"""Regressions for the second re-check of the full-audit fixes (2026-10-06), core: the dollar
budget keeps the worst case of every request that may have been billed."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from controlled_copy.answering.generate import generate
from controlled_copy.ingestion import pipeline
from controlled_copy.limits import worst_case_usd
from controlled_copy.providers import openrouter
from controlled_copy.providers.base import EMBED_ATTEMPTS, MAX_COMPLETION_TOKENS, ProviderError
from controlled_copy.providers.fake import FakeProvider
from controlled_copy.providers.openrouter import OpenRouterProvider

pytestmark = [pytest.mark.integration, pytest.mark.stage1]

DAY = "2000-01-01T00:00:00"
TEXT = "Wet cartons go to quarantine area Q-01 at once."


def _openrouter(handler) -> OpenRouterProvider:
    provider = OpenRouterProvider("not-a-real-key", "https://example.invalid/api/v1", 5.0, {"prompt": 3})
    provider.max_price_embedding = 0.1
    provider._client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://example.invalid/api/v1"
    )
    return provider


def _embedding(cost) -> httpx.Response:
    body = {"data": [{"index": 0, "embedding": [0.1, 0.2]}], "usage": {"prompt_tokens": 12, "cost": cost}}
    return httpx.Response(200, json=body)


def _one_request(settings, text: str = TEXT) -> float:
    return worst_case_usd(len(text.encode()), settings.max_price_embedding_per_million)


@pytest.fixture
def no_backoff(monkeypatch):
    monkeypatch.setattr(openrouter, "RETRY_BACKOFF", (0.0, 0.0))


def test_rck2_02_a_success_after_lost_replies_keeps_the_earlier_requests(services, no_backoff):
    """The first two requests lose their replies (the provider may still bill them), the third
    answers: the batch is booked at the reported cost plus the worst case of the two others."""
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(1)
        if len(sent) < 3:
            raise httpx.ReadTimeout("the reply was lost", request=request)
        return _embedding(0.00005)

    services.provider = _openrouter(handler)
    pipeline.embed_texts(services, [TEXT])
    assert len(sent) == 3
    expected = 0.00005 + 2 * _one_request(services.settings)
    assert services.repo.spent_usd(DAY) == pytest.approx(expected)


def test_rck2_02_a_first_time_success_is_booked_at_its_reported_cost(services, no_backoff):
    services.provider = _openrouter(lambda request: _embedding(0.00005))
    pipeline.embed_texts(services, [TEXT])
    assert services.repo.spent_usd(DAY) == pytest.approx(0.00005)


def test_rck2_02_retries_that_all_fail_keep_the_whole_reservation(services, no_backoff):
    services.provider = _openrouter(lambda request: httpx.Response(503, json={}))
    with pytest.raises(ProviderError):
        pipeline.embed_texts(services, [TEXT])
    expected = EMBED_ATTEMPTS * _one_request(services.settings)
    assert services.repo.spent_usd(DAY) == pytest.approx(expected)


def test_rck2_04_an_embedding_batch_reserves_every_request_it_may_send(services):
    """While a batch is in flight, the day already holds the worst case of all three requests."""
    seen = []

    class Watching(FakeProvider):
        def embed(self, texts, *, model):
            seen.append(services.repo.spent_usd(DAY))
            return super().embed(texts, model=model)

    services.provider = Watching()
    pipeline.embed_texts(services, [TEXT])
    assert seen == [pytest.approx(EMBED_ATTEMPTS * _one_request(services.settings))]


def test_rck2_04_a_generation_reservation_covers_its_prompt(services):
    """A long prompt costs more than the output allowance alone: the reservation held while the
    call runs counts every prompt byte at the prompt cap."""

    class Out(BaseModel):
        ok: bool

    seen = []

    class Watching(FakeProvider):
        def chat_json(self, messages, *, schema, schema_name, model, timeout):
            seen.append(services.repo.spent_usd(DAY))
            return super().chat_json(
                messages, schema=schema, schema_name=schema_name, model=model, timeout=timeout
            )

    services.provider = Watching(responder=lambda request: {"ok": True})
    messages = [{"role": "user", "content": "Ä" * 50_000}]  # 100,000 bytes
    schema = Out.model_json_schema()
    generate(services, messages, schema=schema, schema_name="x", model_cls=Out)
    settings = services.settings
    prompt_bytes = len(json.dumps(messages).encode()) + len(json.dumps(schema).encode())
    full = worst_case_usd(
        prompt_bytes,
        settings.max_price_prompt_per_million,
        MAX_COMPLETION_TOKENS,
        settings.max_price_completion_per_million,
    )
    output_only = worst_case_usd(0, 0.0, MAX_COMPLETION_TOKENS, settings.max_price_completion_per_million)
    assert seen and seen[0] == pytest.approx(full)
    assert seen[0] > output_only + 0.2, "the prompt's 100 KB add about 0.3 USD at 3 USD per million"


@pytest.mark.parametrize("cost", [-4.5, float("nan"), "0.01", True])
def test_rck2_06_an_impossible_reported_cost_is_ignored(cost):
    """Only a non-negative number counts as a reported cost; anything else leaves the call's
    reservation in place (a negative cost would lower the day's total)."""

    def chat(request: httpx.Request) -> httpx.Response:
        body = {"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {"cost": cost}}
        return httpx.Response(200, content=json.dumps(body))

    assert _openrouter(chat).chat_json([], schema={}, schema_name="x", model="m", timeout=5).cost_usd is None
    embedded = _openrouter(
        lambda request: httpx.Response(
            200, content=json.dumps({"data": [{"index": 0, "embedding": [0.1]}], "usage": {"cost": cost}})
        )
    ).embed(["one"], model="baai/bge-m3")
    assert embedded.cost_usd is None and embedded.requests == 1
