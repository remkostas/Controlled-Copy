"""OpenRouter adapter (OpenAI-compatible HTTP API, called with httpx).

Privacy routing on every request: `provider.zdr = true` (zero-data-retention
endpoints only) and `provider.data_collection = "deny"`. Generation requests
also set `require_parameters`, so they only reach providers that honour the
JSON schema (structured outputs). No sampling parameters are sent: several
current models reject `temperature`, and with `require_parameters` an unsupported
parameter would rule out every endpoint.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from controlled_copy.logs import log_event
from controlled_copy.providers.base import (
    ChatResult,
    EmbedResult,
    ProviderBadOutput,
    ProviderError,
    ProviderTimeout,
    ProviderTransient,
)

PRIVACY = {"zdr": True, "data_collection": "deny"}
TRANSIENT_STATUS = frozenset({408, 429, 500, 502, 503, 504})
RETRY_BACKOFF = (1.0, 3.0)


def build_embedding_request(texts: list[str], model: str) -> dict[str, Any]:
    return {"model": model, "input": texts, "provider": dict(PRIVACY)}


def build_chat_request(
    messages: list[dict[str, str]], schema: dict[str, Any], schema_name: str, model: str
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        },
        "provider": {**PRIVACY, "require_parameters": True},
        "max_tokens": 4000,
        "usage": {"include": True},
    }


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key: str, base_url: str, timeout: float) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    def close(self) -> None:
        self._client.close()

    def _post_with_retry(self, path: str, body: dict[str, Any], retries: int) -> dict[str, Any]:
        """Retry transient failures (rate limits, 5xx, network) with a short backoff."""
        for attempt in range(retries + 1):
            try:
                return self._post(path, body)
            except ProviderError as exc:
                if not isinstance(exc, ProviderTransient) or attempt == retries:
                    raise
                log_event("provider_retry", path=path, attempt=attempt + 1, model=str(body.get("model")))
                time.sleep(RETRY_BACKOFF[attempt])
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
            raise kind(f"provider returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderBadOutput("provider returned non-JSON") from exc
        if isinstance(data, dict) and data.get("error"):
            code = data["error"].get("code") if isinstance(data["error"], dict) else None
            log_event("provider_error_body", path=path, status=str(code), model=str(body.get("model")))
            kind = ProviderTransient if code in TRANSIENT_STATUS else ProviderError
            raise kind(f"provider error {code}")
        return data

    def embed(self, texts: list[str], *, model: str) -> EmbedResult:
        data = self._post_with_retry("/embeddings", build_embedding_request(texts, model), retries=2)
        items = data.get("data")
        if not isinstance(items, list) or len(items) != len(texts):
            raise ProviderBadOutput("embedding response has the wrong number of vectors")
        ordered = sorted(items, key=lambda item: item.get("index", 0))
        vectors = [item["embedding"] for item in ordered]
        usage = data.get("usage") or {}
        return EmbedResult(
            vectors=vectors,
            model=str(data.get("model") or model),
            input_tokens=int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0),
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
            "/chat/completions", build_chat_request(messages, schema, schema_name, model), timeout
        )
        try:
            message = data["choices"][0]["message"]
            content = message.get("content")
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderBadOutput("chat response has no message") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderBadOutput("chat response is empty")
        usage = data.get("usage") or {}
        cost = usage.get("cost")
        return ChatResult(
            content=content,
            model=str(data.get("model") or model),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=float(cost) if isinstance(cost, int | float) else None,
            provider=str(data.get("provider")) if data.get("provider") else None,
        )
