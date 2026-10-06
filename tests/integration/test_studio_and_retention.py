"""FR-STU-01, FR-STU-02, FR-RTN-01."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from controlled_copy.purge import purge
from tests.conftest import corpus_file

pytestmark = [pytest.mark.integration, pytest.mark.stage1]


def test_tc_stu_001_briefing_has_all_sections_and_only_verified_citations(visitor, db):
    visitor.upload("sop.md", corpus_file("SOP-INB-001_inbound-receiving_rev3.md"))
    visitor.upload("wi.md", corpus_file("WI-QUA-004_damaged-material_rev2.md"))
    response = visitor.briefing()
    assert response.status_code == 200
    output = response.json()["output"]
    assert [s["title"] for s in output["sections"]] == [
        "Overview",
        "Key points",
        "Important terms",
        "Open questions",
    ]
    texts = {
        r["id"]: r["text"]
        for r in db.execute("SELECT id, text FROM source WHERE notebook_id = ?", (visitor.notebook_id,))
    }
    assert output["citations"]
    for citation in output["citations"]:
        assert texts[citation["source_id"]][citation["start"] : citation["end"]] == citation["quote"]
    for section in output["sections"]:
        for item in section["items"]:
            assert item["cites"], "every item carries at least one verified citation"
    page = visitor.refresh().page
    assert "Briefing" in page and "Key points" in page


def test_tc_stu_001_briefing_drops_items_with_failed_quotes(visitor, fake):

    visitor.paste("Doc", "Pallets are wrapped in foil before storage. Labels face the aisle.")

    def responder(request):
        if request.schema_name != "briefing":
            from controlled_copy.providers.fake import default_responder

            return default_responder(request)
        pid = request.passages()[0][0]
        good = {
            "text": "Pallets are wrapped.",
            "citations": [{"passage_id": pid, "quote": "Pallets are wrapped in foil"}],
        }
        bad = {
            "text": "Pallets are painted.",
            "citations": [{"passage_id": pid, "quote": "Pallets are painted blue"}],
        }
        return {"overview": [good, bad], "key_points": [], "important_terms": [], "open_questions": []}

    fake.responder = responder
    output = visitor.briefing().json()["output"]
    assert [i["text"] for i in output["sections"][0]["items"]] == ["Pallets are wrapped."]
    assert output["removed"] == 1


def test_tc_stu_002_three_suggested_questions_generated_once_per_source_change(visitor, fake):
    visitor.paste("Doc", "Pallets are wrapped in foil before storage. Labels face the aisle.")
    url = f"/notebooks/{visitor.notebook_id}/suggestions"
    first = visitor.client.post(url, headers=visitor.headers)
    second = visitor.client.post(url, headers=visitor.headers)
    assert first.status_code == second.status_code == 200
    assert first.text.count('class="suggestion"') == 3
    assert first.text == second.text
    assert len([c for c in fake.chat_calls if c.schema_name == "suggestions"]) == 1
    visitor.paste("Doc 2", "Forklifts are charged overnight in bay seven.")
    visitor.client.post(url, headers=visitor.headers)
    visitor.client.post(url, headers=visitor.headers)
    assert len([c for c in fake.chat_calls if c.schema_name == "suggestions"]) == 2


def test_tc_rtn_001_sessions_unseen_for_169_hours_are_purged(make_visitor, db, settings, services):
    old, fresh = make_visitor(), make_visitor()
    old.paste("Old", "Old session text about docks.")
    old.upload("old.txt", b"Old uploaded file about pallets.")
    fresh.paste("Fresh", "Fresh session text about docks.")
    old_sid = db.execute("SELECT session_id FROM notebook WHERE id = ?", (old.notebook_id,)).fetchone()[0]
    stale = (datetime.now(UTC) - timedelta(hours=169)).isoformat(timespec="seconds")
    db.execute("UPDATE visitor_session SET last_seen_at = ? WHERE id = ?", (stale, old_sid))
    assert len(list(settings.uploads_dir.iterdir())) == 1

    result = purge(settings, services.repo)
    assert result.sessions == 1 and result.files == 1
    assert db.execute("SELECT COUNT(*) FROM visitor_session WHERE id = ?", (old_sid,)).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM notebook WHERE id = ?", (old.notebook_id,)).fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM source WHERE title IN ('Old', 'old')").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM source WHERE title = 'Fresh'").fetchone()[0] == 1
    assert list(settings.uploads_dir.iterdir()) == []
    # The purged visitor must enter the code again.
    assert old.client.get("/app", follow_redirects=False).status_code == 303


def test_tc_rtn_001_a_session_seen_167_hours_ago_is_kept(visitor, db, settings, services):
    recent = (datetime.now(UTC) - timedelta(hours=167)).isoformat(timespec="seconds")
    db.execute("UPDATE visitor_session SET last_seen_at = ?", (recent,))
    assert purge(settings, services.repo).sessions == 0


def test_tc_stu_001_typed_templates_still_drop_statements_whose_quotes_fail(services, fake, tmp_path):
    """Statement types alone never keep an unverified statement; only an explicit caller can."""
    from controlled_copy.retrieval.search import Passage
    from controlled_copy.studio import engine

    spec = json.loads((engine.TEMPLATE_DIR / "briefing.json").read_text())
    spec["statement_types"] = ["requirement", "inference"]
    path = tmp_path / "typed.json"
    path.write_text(json.dumps(spec))
    template = engine.load_template(path)
    text = "Count every delivery line before posting."
    passage = Passage(
        chunk_id=1,
        source_id="s",
        source_title="SOP",
        source_kind="md",
        locator="4.2",
        page=None,
        char_start=0,
        char_end=len(text),
        text=text,
        metadata=None,
        metadata_origin="none",
        cosine=1.0,
        fused=1.0,
    )

    def invented(request):
        pid = request.passages()[0][0]
        item = {
            "type": "requirement",
            "text": "Never count.",
            "citations": [{"passage_id": pid, "quote": "never count anything"}],
        }
        return {section.key: [item] for section in template.sections}

    fake.responder = invented
    dropped = engine.run_template(services, template, [passage])
    assert all(not s["items"] for s in dropped.output["sections"])
    kept = engine.run_template(services, template, [passage], keep_uncited=True)
    assert all(s["items"][0]["cites"] == [] for s in kept.output["sections"])
