"""FR-IDX-03 for the visitor: an embedding service that stays busy gives a clear, retryable
message and stores nothing; the whole embedding step has a time budget (stage 1)."""

import pytest

from controlled_copy.providers.base import ProviderError

pytestmark = [pytest.mark.integration, pytest.mark.stage1]


def test_tc_idx_003_a_busy_embedding_service_says_so(visitor, fake, db, monkeypatch):
    def rate_limited(texts, *, model):
        raise ProviderError("provider returned HTTP 429", status=429)

    monkeypatch.setattr(fake, "embed", rate_limited)
    response = visitor.upload("note.md", b"# Note\n\nA short note.", expect=503)
    assert "busy" in response.json()["error"] and "Nothing was stored" in response.json()["error"]
    assert (
        db.execute("SELECT COUNT(*) FROM source WHERE notebook_id = ?", (visitor.notebook_id,)).fetchone()[0]
        == 0
    )


def test_tc_idx_003_another_provider_failure_keeps_the_general_message(visitor, fake, monkeypatch):
    def broken(texts, *, model):
        raise ProviderError("provider returned HTTP 401", status=401)

    monkeypatch.setattr(fake, "embed", broken)
    response = visitor.upload("note.md", b"# Note\n\nA short note.", expect=502)
    assert "not available" in response.json()["error"]


def test_tc_idx_003_the_upload_stops_when_its_time_budget_is_used(make_visitor, settings, fake, db):
    """With the budget already used up, no batch starts and the visitor gets the busy message."""
    settings.upload_embedding_budget_seconds = 0.5  # less than the one second a batch needs
    visitor = make_visitor()
    calls = fake.embed_calls
    response = visitor.paste("Long", "Pallets are wrapped twice before storage.", expect=503)
    assert "busy" in response.json()["error"]
    assert fake.embed_calls == calls, "no batch starts after the budget is used up"
    assert (
        db.execute("SELECT COUNT(*) FROM source WHERE notebook_id = ?", (visitor.notebook_id,)).fetchone()[0]
        == 0
    )
