"""OpenRouter adapter (OpenAI-compatible HTTP API, called with httpx).

Privacy routing on every request: `provider.zdr = true` (zero-data-retention
endpoints only) and `provider.data_collection = "deny"`. Generation requests
also set `require_parameters`, so they only reach providers that honour the
JSON schema (structured outputs), and `max_price`, so a model added to the model
picker cannot route to an expensive endpoint; embedding requests carry a prompt
price cap too. Together with the output allowance (`max_tokens`) the caps bound
what one call can cost, which the daily dollar budget reserves before each call.
No sampling parameters are sent:
several current models reject `temperature`, and with `require_parameters` an
unsupported parameter would rule out every endpoint.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any

import httpx

from controlled_copy.logs import log_event
from controlled_copy.providers.base import (
    EMBED_ATTEMPTS,
    MAX_COMPLETION_TOKENS,
    ChatResult,
    EmbedResult,
    ProviderBadOutput,
    ProviderError,
    ProviderTimeout,
    ProviderTransient,
)

PRIVACY: dict[str, Any] = {"zdr": True, "data_collection": "deny"}
TRANSIENT_STATUS = frozenset({408, 429, 500, 502, 503, 504})
# Seconds before retry 1, 2, 3, ...; the last value repeats. A random extra of up to half the
# wait spreads retries from parallel uploads. A provider's Retry-After wins, up to the cap.
RETRY_BACKOFF = (2.0, 4.0, 8.0, 12.0)
RETRY_AFTER_CAP = 15.0


def _retry_wait(attempt: int, retry_after: float | None) -> float:
    base = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
    if retry_after is not None:
        return min(max(retry_after, base), RETRY_AFTER_CAP)
    return base + random.uniform(0, base / 2)  # noqa: S311 - jitter, not security


def _retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header in its seconds form; dates are ignored."""
    try:
        seconds = float(value) if value is not None else None
    except ValueError:
        return None
    return seconds if seconds is not None and math.isfinite(seconds) and seconds >= 0 else None


def build_embedding_request(
    texts: list[str], model: str, max_price_prompt: float | None = None
) -> dict[str, Any]:
    provider: dict[str, Any] = dict(PRIVACY)
    if max_price_prompt:
        provider["max_price"] = {"prompt": max_price_prompt}
    return {"model": model, "input": texts, "provider": provider}


def build_chat_request(
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    model: str,
    max_price: dict[str, float] | None = None,
) -> dict[str, Any]:
    provider: dict[str, Any] = {**PRIVACY, "require_parameters": True}
    if max_price:
        provider["max_price"] = dict(max_price)
    return {
        "model": model,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
        "provider": provider,
        "max_tokens": MAX_COMPLETION_TOKENS,
        "usage": {"include": True},
    }


def _envelope(data: Any) -> dict[str, Any]:
    """The JSON body of a 200 response must be an object; anything else is bad output."""
    if not isinstance(data, dict):
        raise ProviderBadOutput("response is not a JSON object")
    return data


def _usage(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage")
    return usage if isinstance(usage, dict) else {}


def _finite(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _int(value: Any) -> int:
    return int(value) if _finite(value) else 0


def _cost(usage: dict[str, Any]) -> float | None:
    """The reported cost in USD, or None when it is missing or not a sensible amount (a
    negative cost would lower the day's total), so the call keeps its reservation."""
    cost = usage.get("cost")
    return float(cost) if _finite(cost) and cost >= 0 else None


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float,
        max_price: dict[str, float] | None = None,
        max_price_embedding: float | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_price = max_price
        self.max_price_embedding = max_price_embedding
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    def close(self) -> None:
        self._client.close()

    def _post_with_retry(self, path: str, body: dict[str, Any], retries: int) -> tuple[dict[str, Any], int]:
        """Retry transient failures (rate limits, 5xx, network) with a short backoff, but never
        beyond the caller's time limit: a retry that could not finish in time is not started.
        Returns the response and how many requests were sent."""
        started = time.monotonic()
        for attempt in range(retries + 1):
            remaining = self.timeout - (time.monotonic() - started)
            try:
                return self._post(path, body, timeout=max(1.0, remaining)), attempt + 1
            except ProviderError as exc:
                if not isinstance(exc, ProviderTransient) or attempt == retries:
                    raise
                wait = _retry_wait(attempt, exc.retry_after)
                if time.monotonic() - started + wait >= self.timeout:
                    raise
                log_event(
                    "provider_retry",
                    path=path,
                    attempt=attempt + 1,
                    status=str(exc.status),
                    wait_ms=int(wait * 1000),
                    model=str(body.get("model")),
                )
                time.sleep(wait)
        raise AssertionError("unreachable")

    def _post(self, path: str, body: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        started = time.monotonic()
        try:
            kwargs: dict[str, Any] = {"json": body}
            if timeout is not None:
                kwargs["timeout"] = httpx.Timeout(timeout, connect=10.0)
            response = self._client.post(path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("provider timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderTransient(f"provider request failed: {type(exc).__name__}") from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        if response.status_code >= 400:
            log_event(
                "provider_http_error",
                path=path,
                status=response.status_code,
                model=str(body.get("model")),
                duration_ms=duration_ms,
            )
            kind = ProviderTransient if response.status_code in TRANSIENT_STATUS else ProviderError
            raise kind(
                f"provider returned HTTP {response.status_code}",
                status=response.status_code,
                retry_after=_retry_after(response.headers.get("retry-after")),
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderBadOutput("provider returned non-JSON") from exc
        if isinstance(data, dict) and data.get("error"):
            code = data["error"].get("code") if isinstance(data["error"], dict) else None
            log_event("provider_error_body", path=path, status=str(code), model=str(body.get("model")))
            kind = ProviderTransient if code in TRANSIENT_STATUS else ProviderError
            raise kind(f"provider error {code}", status=code if isinstance(code, int) else None)
        return data

    def embed(self, texts: list[str], *, model: str) -> EmbedResult:
        body = build_embedding_request(texts, model, self.max_price_embedding)
        reply, requests = self._post_with_retry("/embeddings", body, retries=EMBED_ATTEMPTS - 1)
        data = _envelope(reply)
        items = data.get("data")
        if not isinstance(items, list) or len(items) != len(texts):
            raise ProviderBadOutput("embedding response has the wrong number of vectors")
        if not all(isinstance(item, dict) for item in items):
            raise ProviderBadOutput("embedding response has a malformed item")
        ordered = sorted(items, key=lambda item: _int(item.get("index")))
        vectors = []
        for item in ordered:
            vector = item.get("embedding")
            if not isinstance(vector, list) or not vector or not all(_finite(v) for v in vector):
                raise ProviderBadOutput("embedding response has a malformed vector")
            vectors.append([float(v) for v in vector])
        usage = _usage(data)
        return EmbedResult(
            vectors=vectors,
            model=str(data.get("model") or model),
            input_tokens=_int(usage.get("prompt_tokens") or usage.get("total_tokens")),
            cost_usd=_cost(usage),
            requests=requests,
        )

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any],
        schema_name: str,
        model: str,
        timeout: float,
    ) -> ChatResult:
        data = self._post(
            "/chat/completions",
            build_chat_request(messages, schema, schema_name, model, self.max_price),
            timeout,
        )
        data = _envelope(data)
        usage = _usage(data)
        cost_usd = _cost(usage)
        choices = data.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            # Billed but unusable: the cost travels with the error into the daily budget.
            raise ProviderBadOutput("chat response has no usable message", cost_usd=cost_usd)
        return ChatResult(
            content=content,
            model=str(data.get("model") or model),
            input_tokens=_int(usage.get("prompt_tokens")),
            output_tokens=_int(usage.get("completion_tokens")),
            cost_usd=cost_usd,
            provider=str(data.get("provider")) if data.get("provider") else None,
        )
