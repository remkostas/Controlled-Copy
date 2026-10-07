"""FR-SRC-01, 02, 06, 08, 09; FR-IDX-04."""

import pytest

from tests.conftest import CORPUS, corpus_file
from tests.helpers.pdf import make_pdf
from tests.helpers.responders import quote_passage_containing

pytestmark = [pytest.mark.integration, pytest.mark.stage1]


def test_tc_src_001_upload_pdf_txt_and_md(visitor, db):
    visitor.upload("manual.pdf", make_pdf(["Page one text about docks.", "Page two text about pallets."]))
    visitor.upload("notes.txt", b"First paragraph about receiving.\n\nSecond paragraph about counting.")
    visitor.upload("sop.md", corpus_file("SOP-INB-001_inbound-receiving_rev3.md"))
    rows = db.execute(
        "SELECT kind, pages, title, metadata_origin FROM source WHERE notebook_id = ? "
        "ORDER BY created_at, rowid",
        (visitor.notebook_id,),
    ).fetchall()
    assert [r["kind"] for r in rows] == ["pdf", "txt", "md"]
    assert rows[0]["pages"] == 2
    assert rows[2]["title"] == "Inbound Receiving Procedure"
    assert rows[2]["metadata_origin"] == "asserted"
    page = visitor.refresh().page
    assert "2 pages" in page
    assert "sections" in page and "SOP-INB-001" in page


def test_tc_src_002_paste_text_with_a_title(visitor, db):
    visitor.paste("Shift handover", "Dock 3 is closed for repairs until Friday.\n\nUse dock 4 instead.")
    row = db.execute(
        "SELECT kind, title, text FROM source WHERE notebook_id = ?", (visitor.notebook_id,)
    ).fetchone()
    assert (row["kind"], row["title"]) == ("paste", "Shift handover")
    assert "Dock 3 is closed" in row["text"]


def test_tc_src_007_pdf_pages_without_text_are_flagged(visitor):
    pdf = make_pdf(["A page with real text about goods receipt.", None, "Another page with text.", None])
    visitor.upload("scan.pdf", pdf)
    assert "2 pages without extractable text" in visitor.refresh().page


def test_tc_src_010_source_selection_limits_the_search(visitor, fake):
    fake.responder = quote_passage_containing("ZEBRAPALLET procedure wraps fragile goods")
    visitor.paste("Kept", "Inbound trucks are unloaded at dock two in the morning.")
    visitor.paste("Deselected", "The ZEBRAPALLET procedure wraps fragile goods in foil before storage.")
    kept, deselected = visitor.sources
    answer = visitor.ask("What is the ZEBRAPALLET procedure?", source_ids=[kept]).json()["answer"]
    assert answer["kind"] == "refusal"
    assert all(c["source_id"] != deselected for c in answer["citations"])
    # Control: with the source selected, the same question is answered from it.
    answer = visitor.ask("What is the ZEBRAPALLET procedure?", source_ids=[kept, deselected]).json()["answer"]
    assert answer["kind"] == "answer"
    assert {c["source_id"] for c in answer["citations"]} == {deselected}


def test_tc_src_011_deleting_a_source_removes_everything_derived(visitor, db, settings, fake):
    fake.responder = quote_passage_containing("UNIQUEMARKER quarantine rule")
    visitor.upload("rule.txt", b"The UNIQUEMARKER quarantine rule applies to wet cartons at receiving.")
    visitor.paste("Other", "Unrelated text about the canteen menu and opening hours.")
    rule, other = visitor.sources
    answer = visitor.ask("What does the UNIQUEMARKER quarantine rule say?").json()["answer"]
    assert answer["kind"] == "answer"
    chunk_ids = [r[0] for r in db.execute("SELECT id FROM chunk WHERE source_id = ?", (rule,))]
    assert chunk_ids

    response = visitor.client.delete(f"/sources/{rule}", headers=visitor.json_headers())
    assert response.status_code == 200
    assert db.execute("SELECT COUNT(*) FROM source WHERE id = ?", (rule,)).fetchone()[0] == 0
    marks = ",".join("?" * len(chunk_ids))
    assert db.execute(f"SELECT COUNT(*) FROM chunk WHERE id IN ({marks})", chunk_ids).fetchone()[0] == 0
    assert (
        db.execute(f"SELECT COUNT(*) FROM chunk_vector WHERE chunk_id IN ({marks})", chunk_ids).fetchone()[0]
        == 0
    )
    assert (
        db.execute(f"SELECT COUNT(*) FROM chunk_fts WHERE rowid IN ({marks})", chunk_ids).fetchone()[0] == 0
    )
    assert (
        db.execute("SELECT COUNT(*) FROM chunk_fts WHERE chunk_fts MATCH 'uniquemarker'").fetchone()[0] == 0
    )
    assert list(settings.uploads_dir.iterdir()) == []
    # The citing answer is marked, and its content is gone.
    row = db.execute(
        "SELECT status, content FROM chat_message WHERE role = 'assistant' AND notebook_id = ?",
        (visitor.notebook_id,),
    ).fetchone()
    assert row["status"] == "source_deleted"
    assert "UNIQUEMARKER" not in row["content"]
    assert "Answer removed" in visitor.refresh().page
    # Searching for its unique text finds nothing now.
    answer = visitor.ask("UNIQUEMARKER quarantine rule", source_ids=[other]).json()["answer"]
    assert answer["kind"] == "refusal"


def test_tc_idx_004_every_chunk_has_one_vector_and_one_index_row(visitor, db):
    for path in sorted(CORPUS.glob("*.md")):
        visitor.upload(path.name, path.read_bytes())
    chunks = db.execute("SELECT COUNT(*) FROM chunk").fetchone()[
        0
    ]  # every chunk in the database, seeded ones too
    assert chunks > 30
    assert db.execute("SELECT COUNT(*) FROM chunk_vector").fetchone()[0] == chunks
    assert db.execute("SELECT COUNT(*) FROM chunk_fts").fetchone()[0] == chunks
    orphans = db.execute(
        "SELECT COUNT(*) FROM chunk c LEFT JOIN chunk_vector v ON v.chunk_id = c.id WHERE v.chunk_id IS NULL"
    ).fetchone()[0]
    assert orphans == 0
