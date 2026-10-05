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


def test_tc_src_011_an_answer_finishing_after_its_source_was_deleted_keeps_no_text(visitor, fake, db):
    import threading
    import time

    visitor.paste("Payroll note", "Employee example earns EUR 7,450 per month according to this note.")
    fake.delay_seconds = 1.0
    results = {}

    def ask():
        results["answer"] = visitor.ask("What does the employee earn per month?")

    thread = threading.Thread(target=ask)
    thread.start()
    time.sleep(0.3)
    deleted = visitor.client.delete(f"/sources/{visitor.sources[0]}", headers=visitor.json_headers())
    thread.join()
    assert deleted.status_code == 200
    rows = db.execute("SELECT role, status, content FROM chat_message").fetchall()
    assert rows and all(r["status"] == "source_deleted" for r in rows)
    assert all("7,450" not in r["content"] and "earn" not in r["content"] for r in rows)
    assert "7,450" not in visitor.refresh().page


def test_tc_src_011_a_briefing_finishing_after_its_source_was_deleted_keeps_no_text(visitor, fake, db):
    import threading
    import time

    visitor.paste("Payroll note", "Employee example earns EUR 7,450 per month according to this note.")
    fake.delay_seconds = 1.0
    thread = threading.Thread(target=visitor.briefing)
    thread.start()
    time.sleep(0.3)
    visitor.client.delete(f"/sources/{visitor.sources[0]}", headers=visitor.json_headers())
    thread.join()
    row = db.execute("SELECT status, output_json, input FROM studio_output").fetchone()
    assert row["status"] == "source_deleted" and "7,450" not in row["output_json"]


def test_tc_src_011_follow_ups_built_on_a_deleted_source_are_removed(visitor, fake, db):
    from tests.helpers.responders import quote_passage_containing

    visitor.paste("Kept", "Pallets are wrapped in foil before storage at dock two.")
    visitor.paste("Gone", "Wet cartons go to quarantine area Q-01 at once.")
    kept, gone = visitor.sources
    fake.responder = quote_passage_containing("Wet cartons go to quarantine area Q-01")
    visitor.ask("Where do wet cartons go?", source_ids=[gone])
    # A follow-up asked with only the other source selected, refused at the floor.
    visitor.ask("and what about the rocket launch schedule?", source_ids=[kept])
    visitor.client.delete(f"/sources/{gone}", headers=visitor.json_headers())
    rows = db.execute("SELECT status, content, search_query FROM chat_message").fetchall()
    assert all(r["status"] == "source_deleted" for r in rows)
    assert all("Q-01" not in (r["content"] or "") and not r["search_query"] for r in rows)


def test_tc_stu_002_suggestions_for_a_changed_source_set_are_not_stored(visitor, services, db):
    visitor.paste("One", "First text about docks.")
    notebook = services.repo.get_notebook(
        db.execute("SELECT session_id FROM notebook").fetchone()[0], visitor.notebook_id
    )
    assert services.repo.set_suggestions(notebook, "stale", ["Q?"], ["not-the-current-source"]) is False
    assert db.execute("SELECT suggestions_json FROM notebook").fetchone()[0] is None


def test_tc_acc_004_parallel_first_visits_create_one_default_notebook(make_visitor, db):
    import threading

    visitor = make_visitor(login=False)
    from tests.conftest import ACCESS_CODE

    visitor.client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
    threads = [threading.Thread(target=visitor.client.get, args=("/app",)) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert db.execute("SELECT COUNT(*) FROM notebook").fetchone()[0] == 1
