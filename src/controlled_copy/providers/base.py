"""Model provider interface and the errors every adapter raises."""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(Exception):
    """The provider failed (network, HTTP error, no endpoint). Message has no content.

    `cost_usd`: what the provider reported for a call that was billed but failed after the
    response arrived (for example malformed output), so the daily budget still counts it."""

    def __init__(self, message: str = "", *, cost_usd: float | None = None) -> None:
        super().__init__(message)
        self.cost_usd = cost_usd


class ProviderTransient(ProviderError):
    """A failure worth retrying: rate limit, server error, network error or timeout."""


class ProviderTimeout(ProviderTransient):
    """The provider did not answer within the time limit."""


class ProviderBadOutput(ProviderError):
    """The provider answered, but not with JSON matching the schema."""


@dataclass(frozen=True)
class ChatResult:
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    provider: str | None = None


# Bounds the cost of every call (full audit re-check RCK-01): the most completion tokens a
# generation may bill, and how many requests one embedding batch may send (first try plus
# retries of transient failures, any of which might be billed).
MAX_COMPLETION_TOKENS = 4000
EMBED_ATTEMPTS = 3


@dataclass(frozen=True)
class EmbedResult:
    vectors: list[list[float]]
    model: str
    input_tokens: int = 0
    extra: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None


class ModelProvider(Protocol):
    name: str

    def embed(self, texts: list[str], *, model: str) -> EmbedResult: ...

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any],
        schema_name: str,
        model: str,
        timeout: float,
    ) -> ChatResult: ...


_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=16, thread_name_prefix="model-call")


def call_with_deadline[T](fn: Callable[[], T], timeout: float) -> T:
    """Run a provider call with a hard overall deadline.

    HTTP client timeouts limit each read, not the whole call; this limits the
    total. A call that overruns keeps running in its worker thread until the
    client's own timeout ends it, but the request is answered on time.
    """
    if not timeout or timeout <= 0:
        raise ValueError("a positive timeout is required")  # None would wait forever
    future = _EXECUTOR.submit(fn)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        raise ProviderTimeout("provider call exceeded the deadline") from exc
