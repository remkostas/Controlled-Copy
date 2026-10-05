"""FR-NB-01, FR-NB-02, FR-SRC-04, FR-SRC-05, FR-SRC-10, FR-FUP-02."""

import re

import pytest

from tests.conftest import corpus_file
from tests.helpers.pdf import make_pdf

pytestmark = [pytest.mark.api, pytest.mark.stage1]


def test_tc_nb_001_create_a_blank_notebook(visitor):
    response = visitor.client.post(
        "/notebooks", data={"title": "Supplier audit"}, headers=visitor.json_headers()
    )
    assert response.status_code == 201
    notebook_id = response.json()["notebook_id"]
    page = visitor.refresh(notebook_id).page
    assert "Supplier audit" in page
    assert "No sources yet" in page
    assert visitor.notebook_id == notebook_id


def test_tc_nb_002_at_most_five_notebooks(visitor, db):
    for i in range(4):  # the first notebook was created on the first visit
        assert (
            visitor.client.post(
                "/notebooks", data={"title": f"NB {i}"}, headers=visitor.json_headers()
            ).status_code
            == 201
        )
    response = visitor.client.post("/notebooks", data={"title": "Sixth"}, headers=visitor.json_headers())
    assert response.status_code == 409
    assert "at most 5 notebooks" in response.json()["error"]
    assert db.execute("SELECT COUNT(*) FROM notebook").fetchone()[0] == 5
    assert "New notebook" not in visitor.refresh().page


def test_tc_src_005_size_and_page_limits(visitor, db):
    too_big = b"a" * (10 * 1024 * 1024 + 1)
    response = visitor.upload("big.txt", too_big, expect=413)
    assert "larger than 10 MB" in response.json()["error"]
    response = visitor.upload("long.pdf", make_pdf([f"Page {i}" for i in range(151)]), expect=413)
    assert "151 pages; the limit is 150" in response.json()["error"]
    assert db.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 0


def test_tc_src_005_body_far_over_the_limit_is_cut_off_before_parsing(visitor):
    huge = b"a" * (12 * 1024 * 1024)
    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/sources",
        files={"file": ("x.txt", huge)},
        headers=visitor.json_headers(),
    )
    assert response.status_code == 413


def test_tc_src_006_empty_inputs_are_rejected(visitor, db):
    response = visitor.upload("empty.txt", b"", expect=422)
    assert "empty" in response.json()["error"]
    response = visitor.paste("Blank", "   \n\t  ", expect=422)
    assert "empty" in response.json()["error"]
    assert db.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 0


def test_tc_src_012_viewer_shows_exact_text_marks_the_passage_and_shows_metadata(visitor, db):
    visitor.upload("sop.md", corpus_file("SOP-INB-001_inbound-receiving_rev3.md"))
    source_id = visitor.sources[0]
    text = db.execute("SELECT text FROM source WHERE id = ?", (source_id,)).fetchone()[0]
    passage = "Deviations of up to 2% of the ordered quantity or 2 units"
    start = text.index(passage)
    response = visitor.client.get(
        f"/sources/{source_id}?start={start}&end={start + len(passage)}", headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    body = response.text
    assert f'<mark id="cited">{passage}</mark>' in body
    assert "SOP-INB-001" in body and "approved" in body and "HAM-01" in body and "2026-01-01" in body
    assert "4.2 Quantity check and tolerance" in body  # focus label names the section
    visible = re.sub(
        r"<[^>]+>",
        "",
        body[
            body.index('<div class="doc-text">') : body.index("</div>", body.index('<div class="doc-text">'))
        ],
    )
    import html as html_lib

    assert html_lib.unescape(visible.replace('<div class="doc-text">', "")) == text


def test_tc_src_012_viewer_without_htmx_renders_the_workspace_with_the_source_open(visitor):
    visitor.paste("Notes", "Dock 3 is closed.")
    page = visitor.client.get(f"/sources/{visitor.sources[0]}").text
    assert "is-reading" in page and "Dock 3 is closed." in page


def test_tc_fup_002_the_rewritten_question_is_shown(visitor):
    visitor.upload("wi.md", corpus_file("WI-QUA-004_damaged-material_rev2.md"))
    visitor.ask("How is damaged outer packaging handled?")
    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/ask",
        data={"question": "and if it is wet?", "source_ids": visitor.sources},
        headers={**visitor.headers, "HX-Request": "true"},
    )
    assert response.status_code == 200
    assert 'class="searched"' in response.text
    assert "Searched for <q>" in response.text and "outer packaging" in response.text


def test_tc_fup_002_an_unchanged_rewrite_is_not_shown(visitor, fake):
    visitor.upload("wi.md", corpus_file("WI-QUA-004_damaged-material_rev2.md"))
    visitor.ask("How is damaged outer packaging handled?")
    second = visitor.ask("What should happen when a seal is broken at receipt?").json()
    assert [c.schema_name for c in fake.chat_calls].count("rewrite") == 1
    assert second["search_query"] is None
