"""Regressions for the full audit of 2026-10-06 (reviews/full-audit-2026-10-06), governed layer."""

import json

import pytest

from tests.helpers.cards import card_responder, empty_card, passage_with

pytestmark = [pytest.mark.integration, pytest.mark.stage2]


def htmx_card(workspace, situation, source_ids=None):
    return workspace.card(situation, source_ids=source_ids, htmx=True)


def test_req_01_a_refused_card_renders_and_the_notebook_still_loads(workspace, fake, db):
    calls = len(fake.chat_calls)
    response = htmx_card(workspace, "What is the forklift speed limit in the yard?")
    assert response.status_code == 200, response.text
    assert "Not in the selected sources" in response.text
    assert len(fake.chat_calls) == calls, "no generation call for a refusal"
    page = workspace.visitor.client.get(f"/app?nb={workspace.id}")
    assert page.status_code == 200 and "Not in the selected sources" in page.text


def test_req_01_cards_stored_before_the_fix_still_render(workspace, db):
    workspace.card("What is the forklift speed limit in the yard?")
    row = db.execute(
        "SELECT id, output_json FROM studio_output WHERE notebook_id = ?", (workspace.id,)
    ).fetchone()
    output = json.loads(row["output_json"])
    for key in ("consulted", "not_selected", "fallback_escalation"):
        output["card"].pop(key, None)  # the shape the earlier code stored
    db.execute("UPDATE studio_output SET output_json = ? WHERE id = ?", (json.dumps(output), row["id"]))
    db.commit()
    assert workspace.visitor.client.get(f"/app?nb={workspace.id}").status_code == 200


def personal_doc(visitor, document_id, revision, text):
    front = (
        f"---\ndocument_id: {document_id}\nrevision: {revision}\nstatus: approved\n"
        f"effective_from: 2026-01-01\nsite: all\n---\n# {document_id} rev {revision}\n\n{text}\n"
    )
    return visitor.upload(f"{document_id}-{revision}.md", front.encode()).json()["source_id"]


def test_gov_01_an_unselected_newer_revision_still_supersedes_the_older_one(visitor, fake):
    old = personal_doc(visitor, "POST-1", "1", "Post damaged material directly to unrestricted stock.")
    personal_doc(visitor, "POST-1", "2", "Post damaged material to blocked stock pending inspection.")

    def build(request):
        pid, quote = passage_with(request, "Post damaged material directly to unrestricted stock")
        return empty_card(
            required_actions=[
                {
                    "type": "requirement",
                    "text": "Post to unrestricted.",
                    "citations": [{"passage_id": pid, "quote": quote}],
                }
            ]
        )

    fake.responder = card_responder(build)
    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/studio/resolution-card",
        data={
            "situation": "Damaged material arrived. Where do I post it?",
            "site": "HAM-01",
            "source_ids": [old],
        },
        headers=visitor.json_headers(),
    )
    card = response.json()["output"]["card"]
    assert card["status"] != "supported" and card["used"] == []
    excluded = {d["label"]: d["reason"] for d in card["excluded"]}
    assert excluded["POST-1 rev 1"] == "superseded by POST-1 rev 2"
    assert [d["label"] for d in card["not_selected"]] == ["POST-1 rev 2"]
    assert any("not selected: POST-1 rev 2" in r for r in card["reasons"])


def test_gov_02_deselecting_the_code_guide_keeps_an_unknown_code_unknown(workspace, db, fake):
    matrix = db.execute(
        "SELECT id FROM source WHERE notebook_id = ? AND metadata_json LIKE '%MATRIX-ESC-001%'",
        (workspace.id,),
    ).fetchone()[0]

    def build(request):
        pid, quote = passage_with(request, "unknown error codes")
        return empty_card(
            required_actions=[
                {
                    "type": "requirement",
                    "text": "Escalate.",
                    "citations": [{"passage_id": pid, "quote": quote}],
                }
            ]
        )

    fake.responder = card_responder(build)
    card = workspace.card("The WMS shows the unknown error GR-299.", source_ids=[matrix]).json()["output"][
        "card"
    ]
    assert card["undocumented"] == ["GR-299"]
    assert card["status"] == "expert_confirmation"


def test_gov_03_expert_confirmation_without_a_documented_escalation_names_who_decides(visitor, db):
    personal_doc(visitor, "FUT-1", "1", "Future instruction about WI-TEST-001 handling.")
    db.execute("UPDATE source SET metadata_json = replace(metadata_json, '2026-01-01', '2099-01-01')")
    db.commit()
    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/studio/resolution-card",
        data={
            "situation": "What does FUT-1 require for WI-TEST-001?",
            "site": "HAM-01",
            "source_ids": visitor.sources,
        },
        headers=visitor.json_headers(),
    )
    card = response.json()["output"]["card"]
    assert card["status"] == "expert_confirmation"
    assert card["fallback_escalation"].startswith("Stop and ask the person responsible")
    page = visitor.client.get(f"/app?nb={visitor.notebook_id}").text
    assert "standard escalation, not taken from the documents" in page
