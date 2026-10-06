"""One structured model call with a single fallback attempt.

Attempt 1 uses the primary model. On a provider error, a timeout or output
that is not valid JSON for the schema, attempt 2 uses the fallback model (or
the primary again if both are the same). After that, a user-facing error.
Every attempt is counted against the budget and logged without content.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from controlled_copy.errors import PROVIDER_UNAVAILABLE, UserFacingError
from controlled_copy.logs import log_event
from controlled_copy.providers.base import (
    ChatResult,
    ProviderBadOutput,
    ProviderError,
    ProviderTimeout,
    call_with_deadline,
)
from controlled_copy.services import Services

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class GenerationError(UserFacingError):
    """The model call failed twice."""


def parse_payload[M: BaseModel](content: str, model_cls: type[M]) -> M:
    fenced = _FENCE.match(content)
    raw = fenced.group(1) if fenced else content
    try:
        return model_cls.model_validate(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        # Never log or re-raise the validation message: it can contain model output.
        raise ProviderBadOutput("output does not match the schema") from exc


def generate[M: BaseModel](
    services: Services,
    messages: list[dict[str, str]],
    *,
    schema: dict[str, Any],
    schema_name: str,
    model_cls: type[M],
) -> tuple[M, ChatResult]:
    settings = services.settings
    models = [settings.model_generation, settings.model_generation_fallback or settings.model_generation]
    timeout = settings.provider_timeout_seconds
    failure: ProviderError | None = None
    for attempt, model in enumerate(models, start=1):
        call_id = services.budget.consume(services.session_id, schema_name)  # LimitExceeded is user-facing
        started = time.monotonic()
        try:
            result = call_with_deadline(
                lambda model=model: services.provider.chat_json(
                    messages, schema=schema, schema_name=schema_name, model=model, timeout=timeout
                ),
                timeout,
            )
            payload = parse_payload(result.content, model_cls)
        except ProviderError as exc:
            failure = exc
            log_event(
                "model_call",
                session=services.session_id,
                kind=schema_name,
                model=model,
                attempt=attempt,
                outcome="failed",
                error_type=type(exc).__name__,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            continue
        services.budget.add_cost(call_id, result.cost_usd)
        log_event(
            "model_call",
            session=services.session_id,
            kind=schema_name,
            model=result.model,
            provider=result.provider,
            attempt=attempt,
            outcome="ok",
            duration_ms=int((time.monotonic() - started) * 1000),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cost_usd=result.cost_usd,
        )
        return payload, result
    if isinstance(failure, ProviderTimeout):
        raise GenerationError(
            f"The model provider did not answer within {int(timeout)} seconds, twice. Please try again.", 504
        )
    if isinstance(failure, ProviderBadOutput):
        raise GenerationError(
            "The model returned an answer in an unexpected format twice. Please try again.", 502
        )
    raise GenerationError(PROVIDER_UNAVAILABLE, 502)
