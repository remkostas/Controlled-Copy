"""Regression tests for findings of the stage 1 code review (each maps to its TC)."""

import threading

import pytest

from controlled_copy.limits import AccessLimiter, Budget, LimitExceeded
from controlled_copy.storage.db import connect
from controlled_copy.storage.repo import Repo
from controlled_copy.studio.engine import select_overview_passages
from tests.helpers.responders import answer_with

pytestmark = [pytest.mark.integration, pytest.mark.stage1]


def test_tc_stu_001_briefing_passages_cover_the_whole_document(visitor, services, db):
    paragraphs = [f"Section {i} marker{i:02d}. " + "filler words " * 70 for i in range(29)]
    visitor.paste("Long", "\n\n".join(paragraphs))
    passages = select_overview_passages(services, visitor.sources, 14000)
    ordinals = sorted(
        db.execute("SELECT ordinal FROM chunk WHERE id = ?", (p.chunk_id,)).fetchone()[0] for p in passages
    )
    total = db.execute("SELECT COUNT(*) FROM chunk").fetchone()[0]
    assert total >= 25
    assert ordinals[-1] >= total * 0.75, f"briefing stops at chunk {ordinals[-1]} of {total}"


def test_tc_ret_002_vectors_of_another_embedding_model_are_ignored(visitor, services, db):
    visitor.paste("Doc", "Error GR-204 means the quantity is above the open order quantity.")
    db.execute("UPDATE chunk_vector SET model = 'other/model', vector = zeroblob(16), dim = 4")
    from controlled_copy.retrieval.search import retrieve

    result = retrieve(services, visitor.sources, "What does GR-204 mean?")
    assert result.passages, "full-text search still finds the passage"
    assert result.best_cosine == 0.0


def test_tc_src_011_answers_and_outputs_built_from_a_deleted_source_are_removed(visitor, fake, db):
    visitor.paste("Kept", "Pallets are wrapped in foil before storage.")
    visitor.paste("Gone", "Wet cartons go to quarantine area Q-01 at once.")

    def refuse_with_derived_reason(passages):
        return {"statements": [], "unanswerable": ["The passages only say wet cartons go to Q-01."]}

    fake.responder = answer_with(refuse_with_derived_reason)
    assert visitor.ask("Where do wet cartons go?").json()["answer"]["kind"] == "refusal"
    visitor.ask("and what then?")
    assert visitor.briefing().status_code == 200
    gone = visitor.sources[1]
    visitor.client.delete(f"/sources/{gone}", headers=visitor.json_headers())
    rows = db.execute(
        "SELECT status, content, search_query FROM chat_message WHERE role = 'assistant'"
    ).fetchall()
    assert rows and all(r["status"] == "source_deleted" for r in rows)
    assert all("Q-01" not in r["content"] and r["search_query"] is None for r in rows)
    output = db.execute("SELECT status, output_json FROM studio_output").fetchone()
    assert output["status"] == "source_deleted" and "Q-01" not in output["output_json"]


def test_tc_src_005_streamed_body_over_the_limit_gets_413_with_security_headers(visitor):
    def body():
        for _ in range(12):
            yield b"x" * (1024 * 1024)

    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/sources",
        content=body(),
        headers={**visitor.json_headers(), "Content-Type": "multipart/form-data; boundary=zzz"},
    )
    assert response.status_code == 413
    assert "too large" in response.text
    assert "content-security-policy" in response.headers


def test_tc_src_005_source_limit_is_enforced_inside_the_write(visitor, settings, db):
    settings.max_sources_per_notebook = 2
    visitor.paste("One", "First text about docks.")
    visitor.paste("Two", "Second text about pallets.")
    response = visitor.paste("Three", "Third text about labels.", expect=409)
    assert "at most 2 sources" in response.json()["error"]
    assert db.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 2


def test_tc_lim_002_parallel_calls_cannot_overshoot_the_daily_budget(settings, db):
    settings.model_calls_per_day = 5
    errors: list[str] = []
    successes: list[int] = []

    def worker() -> None:
        conn = connect(settings.db_path)
        budget = Budget(settings, Repo(conn))
        try:
            for _ in range(3):
                try:
                    budget.consume(None, "answer")
                    successes.append(1)
                except LimitExceeded:
                    errors.append("limit")
        finally:
            conn.close()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(successes) == 5
    assert db.execute("SELECT COUNT(*) FROM model_call").fetchone()[0] == 5


def test_tc_acc_003_access_limiter_memory_is_bounded():
    limiter = AccessLimiter(attempts_per_hour=10)
    limiter.MAX_TRACKED = 50
    for i in range(500):
        limiter.record_failure(f"10.0.{i // 256}.{i % 256}")
        assert not limiter.blocked(f"192.168.0.{i % 256}")
    assert len(limiter._failures) <= 50
