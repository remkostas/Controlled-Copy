"""Regressions for the Codex review of PR #1 (reviews/PR-1-codex.md), one test per finding."""

from __future__ import annotations

import pytest

from controlled_copy.providers.fake import default_responder

pytestmark = [pytest.mark.integration, pytest.mark.stage1]

CANARY = "7,450"


def deleting_responder(visitor, schema_name: str):
    """A model that, while answering, sees its source deleted through the real endpoint."""

    def responder(request):
        if request.schema_name == schema_name and visitor.sources:
            source = visitor.sources.pop()
            response = visitor.client.delete(f"/sources/{source}", headers=visitor.json_headers())
            assert response.status_code == 200
        return default_responder(request)

    return responder


def payroll(visitor):
    visitor.paste("Payroll note", f"Employee example earns EUR {CANARY} per month according to this note.")


def test_tc_src_011_f1_a_chat_answer_whose_source_was_deleted_mid_answer_is_not_returned(visitor, fake):
    payroll(visitor)
    fake.responder = deleting_responder(visitor, "answer")
    as_json = visitor.ask("What does the employee earn per month?")
    assert as_json.status_code == 200
    assert CANARY not in as_json.text and as_json.json()["answer"]["kind"] == "tombstone"
    payroll(visitor)
    fake.responder = deleting_responder(visitor, "answer")
    as_html = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/ask",
        data={"question": "What does the employee earn per month?", "source_ids": visitor.sources},
        headers=visitor.headers,
    )
    assert as_html.status_code == 200
    assert CANARY not in as_html.text and "Answer removed" in as_html.text


def test_tc_src_011_f1_a_briefing_whose_source_was_deleted_mid_generation_is_not_returned(visitor, fake):
    payroll(visitor)
    fake.responder = deleting_responder(visitor, "briefing")
    response = visitor.briefing()
    assert response.status_code == 200
    assert CANARY not in response.text and response.json()["output"] == {"kind": "tombstone"}


def test_tc_src_011_f1_suggestions_for_a_source_deleted_mid_generation_are_not_shown(visitor, fake):
    payroll(visitor)
    fake.responder = deleting_responder(visitor, "suggestions")
    response = visitor.client.post(f"/notebooks/{visitor.notebook_id}/suggestions", headers=visitor.headers)
    assert response.status_code == 200 and CANARY not in response.text
    assert "suggestion" not in response.text.replace('id="suggestions"', "")


WORD = "uniquedeletioncanarylongword"


def file_bytes(settings) -> bytes:
    path = settings.db_path
    wal = path.with_name(path.name + "-wal")
    return path.read_bytes() + (wal.read_bytes() if wal.exists() else b"")


def test_tc_src_011_f2_deleted_words_leave_the_full_text_index_and_the_database_file(visitor, settings, db):
    for i in range(8):  # separate inserts: several index segments
        text = f"Note {i} about dock procedures and pallets." + (f" {WORD} appears here." if i == 3 else "")
        visitor.paste(f"Note {i}", text)
    assert WORD.encode() in file_bytes(settings)
    target = visitor.sources[3]
    assert visitor.client.delete(f"/sources/{target}", headers=visitor.json_headers()).status_code == 200
    assert WORD.encode() not in file_bytes(settings), "no index segment, page or WAL frame keeps the word"
    assert db.execute("SELECT COUNT(*) FROM chunk_fts WHERE chunk_fts MATCH ?", (WORD,)).fetchone()[0] == 0


def test_tc_nb_003_f2_deleting_a_notebook_also_clears_the_index(visitor, settings):
    visitor.paste("Secret", f"The {WORD} is only in this notebook.")
    visitor.paste("Other", "Ordinary text about dock procedures.")
    response = visitor.client.delete(f"/notebooks/{visitor.notebook_id}", headers=visitor.json_headers())
    assert response.status_code in (200, 303)
    assert WORD.encode() not in file_bytes(settings)


def test_tc_rtn_001_f2_the_hourly_purge_also_clears_the_index(visitor, settings, db):
    from datetime import UTC, datetime, timedelta

    from controlled_copy.purge import purge
    from controlled_copy.storage.repo import Repo

    visitor.paste("Secret", f"The {WORD} is only in this session.")
    purge(settings, Repo(db), datetime.now(UTC) + timedelta(hours=settings.retention_hours + 1))
    assert WORD.encode() not in file_bytes(settings)


def test_tc_sec_002_f3_suggestions_cannot_be_generated_cross_site(visitor, fake):
    visitor.paste("Doc", "Pallets are wrapped in foil before storage. Labels face the aisle.")
    url = f"/notebooks/{visitor.notebook_id}/suggestions"
    calls = len(fake.chat_calls)
    assert visitor.client.get(url).status_code == 405, "no GET that writes"
    foreign = visitor.client.post(url, headers={"Origin": "https://evil.example"})
    assert foreign.status_code == 403
    no_token = visitor.client.post(url)
    assert no_token.status_code == 403
    assert len(fake.chat_calls) == calls, "no model call, no budget spent"
    assert visitor.client.post(url, headers=visitor.headers).text.count('class="suggestion"') == 3


def test_tc_src_009_f4_deeply_nested_front_matter_is_malformed_metadata_not_a_crash(visitor, db):
    from controlled_copy.ingestion.frontmatter import MALFORMED, split_front_matter

    text = "---\ntitle: " + "[" * 600 + "x" + "]" * 600 + "\n---\nOrdinary document text."
    meta, body, warning = split_front_matter(text)
    assert meta is None and warning == MALFORMED and body == "Ordinary document text."
    response = visitor.upload("nested.md", text.encode())
    assert response.status_code == 201
    warnings = db.execute(
        "SELECT warnings_json FROM source WHERE id = ?", (response.json()["source_id"],)
    ).fetchone()[0]
    assert "front matter could not be read" in warnings


@pytest.mark.parametrize(
    "questions",
    [[], ["", "  "], ["Same?", "same?", "Same?"], ["One?", "Two?"]],
    ids=["empty", "blank", "duplicates", "short"],
)
def test_tc_stu_002_f5_short_suggestion_lists_are_retried_and_never_cached(visitor, fake, db, questions):
    visitor.paste("Doc", "Pallets are wrapped in foil before storage. Labels face the aisle.")

    def responder(request):
        if request.schema_name == "suggestions":
            return {"questions": questions}
        return default_responder(request)

    fake.responder = responder
    url = f"/notebooks/{visitor.notebook_id}/suggestions"
    first = visitor.client.post(url, headers=visitor.headers)
    assert first.status_code == 200 and 'class="suggestion"' not in first.text
    calls = [c for c in fake.chat_calls if c.schema_name == "suggestions"]
    assert len(calls) == 2, "the malformed list was retried once with the fallback model"
    cached = db.execute("SELECT suggestions_json FROM notebook WHERE id = ?", (visitor.notebook_id,))
    assert cached.fetchone()[0] is None
    fake.responder = default_responder
    second = visitor.client.post(url, headers=visitor.headers)
    assert second.text.count('class="suggestion"') == 3, "a later request tries again"


def test_tc_src_005_f6_a_notebook_holds_a_bounded_amount_of_text(settings):
    from fastapi.testclient import TestClient

    from controlled_copy.app import create_app
    from controlled_copy.providers.fake import FakeProvider
    from tests.conftest import Visitor

    fake = FakeProvider()
    app = create_app(settings.model_copy(update={"max_notebook_chars": 100}), fake, run_purge=False)
    with TestClient(app) as client:
        visitor = Visitor(client).login()
        visitor.paste("First", "a" * 60)
        visitor.paste("Exactly to the limit", "b" * 40)
        embeds = fake.embed_calls
        refused = visitor.paste("One too many", "c", expect=409)
        assert "at most 100 characters" in refused.json()["error"]
        assert fake.embed_calls == embeds, "refused before any embedding call"
        visitor.client.delete(f"/sources/{visitor.sources[0]}", headers=visitor.json_headers())
        visitor.paste("Fits again", "d" * 60)


def test_healthz_reports_a_database_that_cannot_be_opened(settings, tmp_path):
    from fastapi.testclient import TestClient

    from controlled_copy.app import create_app
    from controlled_copy.providers.fake import FakeProvider

    app = create_app(settings, FakeProvider(), run_purge=False)
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        app.state.settings = settings.model_copy(update={"data_dir": tmp_path / "missing" / "dir"})
        broken = client.get("/healthz")
        assert broken.status_code == 503 and broken.json() == {"status": "database unavailable"}
