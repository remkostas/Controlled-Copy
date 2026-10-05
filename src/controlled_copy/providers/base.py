"""Model provider interface and the errors every adapter raises."""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(Exception):
    """The provider failed (network, HTTP error, no endpoint). Message has no content."""


class ProviderTimeout(ProviderError):
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


@dataclass(frozen=True)
class EmbedResult:
    vectors: list[list[float]]
    model: str
    input_tokens: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


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
    future = _EXECUTOR.submit(fn)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError as exc:
        future.cancel()
        raise ProviderTimeout("provider call exceeded the deadline") from exc
