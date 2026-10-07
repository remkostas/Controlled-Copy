"""FR-IDX-03 under load: embedding rate limits are retried long enough for a daytime upload,
within a time budget, and a failure says the service is busy (stage 1)."""

import httpx
import pytest

from controlled_copy.providers import openrouter
from controlled_copy.providers.base import EMBED_ATTEMPTS, ProviderError

pytestmark = [pytest.mark.unit, pytest.mark.stage1]

OK = {"data": [{"index": 0, "embedding": [1.0]}], "usage": {"prompt_tokens": 1, "cost": 0.0}}


def provider_with(replies, timeout=60.0):
    provider = openrouter.OpenRouterProvider("key", "https://example.invalid/api/v1", timeout)
    sent = []

    def handler(request):
        sent.append(request)
        return next(replies)

    provider._client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://example.invalid/api/v1"
    )
    return provider, sent


@pytest.fixture
def waits(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(openrouter.time, "sleep", slept.append)
    return slept


def test_tc_idx_003_a_burst_of_rate_limits_is_ridden_out(waits):
    replies = iter([httpx.Response(429)] * (EMBED_ATTEMPTS - 1) + [httpx.Response(200, json=OK)])
    provider, sent = provider_with(replies)
    result = provider.embed(["x"], model="baai/bge-m3")
    assert result.vectors == [[1.0]] and result.requests == EMBED_ATTEMPTS == len(sent)
    assert len(waits) == EMBED_ATTEMPTS - 1
    assert all(base <= wait <= base * 1.5 for base, wait in zip((2, 4, 8, 12), waits, strict=False))


def test_tc_idx_003_retry_after_is_honoured_and_capped(waits):
    replies = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(429, headers={"Retry-After": "120"}),
            httpx.Response(200, json=OK),
        ]
    )
    provider, _ = provider_with(replies)
    provider.embed(["x"], model="baai/bge-m3")
    assert waits == [7.0, openrouter.RETRY_AFTER_CAP]


def test_tc_idx_003_persistent_rate_limits_end_with_the_status(waits):
    replies = iter([httpx.Response(429)] * EMBED_ATTEMPTS)
    provider, sent = provider_with(replies)
    with pytest.raises(ProviderError) as failure:
        provider.embed(["x"], model="baai/bge-m3")
    assert failure.value.status == 429 and len(sent) == EMBED_ATTEMPTS


def test_tc_idx_003_a_non_transient_error_is_not_retried(waits):
    provider, sent = provider_with(iter([httpx.Response(400)]))
    with pytest.raises(ProviderError) as failure:
        provider.embed(["x"], model="baai/bge-m3")
    assert failure.value.status == 400 and len(sent) == 1 and waits == []


@pytest.mark.parametrize(
    ("header", "expected"), [("5", 5.0), ("0.5", 0.5), ("soon", None), ("-1", None), (None, None)]
)
def test_tc_idx_003_retry_after_parsing(header, expected):
    assert openrouter._retry_after(header) == expected
