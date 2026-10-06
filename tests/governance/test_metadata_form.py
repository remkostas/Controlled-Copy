"""FR-META-01 and FR-META-02 through the app (stage 3 on the governed layer)."""

import json

import pytest

from tests.helpers.cards import card_responder, empty_card, passage_with

pytestmark = [pytest.mark.integration, pytest.mark.stage3]

FORM = {
    "doc_document_id": "DOCK-RULE-1",
    "doc_revision": "2",
    "doc_status": "approved",
    "doc_effective_from": "2026-01-01",
    "doc_site": "all",
    "doc_roles": "",
}


def paste(visitor, form, text="Every damaged pallet is photographed before unloading.", **extra):
    return visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/sources",
        data={"title": "Dock rule", "text": text, **form, **extra},
        headers=visitor.json_headers(),
    )


def test_tc_meta_002_typed_metadata_is_stored_as_asserted(visitor, db):
    response = paste(visitor, FORM)
    assert response.status_code == 201, response.text
    row = db.execute(
        "SELECT metadata_json, metadata_origin FROM source WHERE id = ?", (response.json()["source_id"],)
    )
    meta, origin = row.fetchone()
    assert origin == "asserted"
    assert json.loads(meta)["document_id"] == "DOCK-RULE-1"
    page = visitor.refresh().page
    assert "Document control (optional)" in page and 'name="doc_status"' in page


def test_tc_meta_002_typed_metadata_replaces_front_matter(visitor, db):
    data = b"---\ndocument_id: FILE-1\nstatus: draft\n---\n# Note\n\nCount every pallet.\n"
    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/sources",
        files={"file": ("note.md", data, "application/octet-stream")},
        data=FORM,
        headers=visitor.json_headers(),
    )
    assert response.status_code == 201, response.text
    meta = json.loads(
        db.execute(
            "SELECT metadata_json FROM source WHERE id = ?", (response.json()["source_id"],)
        ).fetchone()[0]
    )
    assert meta["document_id"] == "DOCK-RULE-1" and meta["status"] == "approved"


def test_tc_meta_002_an_unusable_form_stores_nothing(visitor, db):
    response = paste(visitor, {**FORM, "doc_status": "released"})
    assert response.status_code == 422
    assert "Choose a status" in response.json()["error"]
    count = db.execute("SELECT COUNT(*) FROM source WHERE notebook_id = ?", (visitor.notebook_id,))
    assert count.fetchone()[0] == 0


def test_tc_meta_002_a_typed_document_supports_a_card_in_a_personal_notebook(visitor, fake):
    source_id = paste(visitor, FORM).json()["source_id"]

    def build(request):
        pid, quote = passage_with(request, "Every damaged pallet is photographed before unloading")
        return empty_card(
            required_actions=[
                {
                    "type": "requirement",
                    "text": "Photograph it.",
                    "citations": [{"passage_id": pid, "quote": quote}],
                }
            ]
        )

    fake.responder = card_responder(build)
    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/studio/resolution-card",
        data={
            "situation": "A damaged pallet arrived at the dock.",
            "site": "HAM-01",
            "source_ids": [source_id],
        },
        headers=visitor.json_headers(),
    )
    card = response.json()["output"]["card"]
    assert card["status"] == "supported"
    assert card["reasons"][0] == "the approval of these documents is asserted by the uploader, not checked"
