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


def _source_id(db, workspace, document_id):
    return db.execute(
        "SELECT id FROM source WHERE notebook_id = ? AND metadata_json LIKE ?",
        (workspace.id, f"%{document_id}%"),
    ).fetchone()[0]


def _escalating(text="Escalate.", needle="unknown error codes", escalation=None):
    def build(request):
        pid, quote = passage_with(request, needle)
        required = [{"type": "requirement", "text": text, "citations": [{"passage_id": pid, "quote": quote}]}]
        return empty_card(required_actions=required, escalation=escalation(pid, quote) if escalation else [])

    return card_responder(build)


def test_rck_08_a_code_only_an_unselected_document_covers_is_documented(workspace, db, fake):
    """Full audit re-check RCK-08: with only the matrix selected, GR-204 is documented by
    GUIDE-WMS-003 (applicable, not selected) and must not be called undocumented; the card
    still asks for confirmation, because the evidence does not cover it. GR-299 stays
    undocumented."""
    matrix = _source_id(db, workspace, "MATRIX-ESC-001")
    fake.responder = _escalating()
    card = workspace.card("The WMS shows GR-204 and then GR-299.", source_ids=[matrix]).json()["output"][
        "card"
    ]
    assert card["undocumented"] == ["GR-299"]
    assert card["status"] == "expert_confirmation"
    assert "GR-204 is covered by GUIDE-WMS-003 rev 1, which is not selected" in card["reasons"]
    assert "no applicable approved document covers GR-299" in card["reasons"]


def test_rck_07_an_uncited_recommendation_does_not_hide_who_decides(workspace, db, fake):
    """Full audit re-check RCK-07: a recommendation without a quote in the escalation section
    names nobody from the documents, so the standard line is still shown."""
    matrix = _source_id(db, workspace, "MATRIX-ESC-001")
    vague = [{"type": "recommendation", "text": "Gather more information before deciding.", "citations": []}]
    fake.responder = _escalating(escalation=lambda pid, quote: vague)
    card = workspace.card("The WMS shows the unknown error GR-299.", source_ids=[matrix]).json()["output"][
        "card"
    ]
    assert card["status"] == "expert_confirmation"
    assert card["fallback_escalation"].startswith("Stop and ask the person responsible")


def test_rck_07_a_documented_escalation_replaces_the_standard_line(workspace, db, fake):
    matrix = _source_id(db, workspace, "MATRIX-ESC-001")

    def documented(pid, quote):
        cite = [{"passage_id": pid, "quote": quote}]
        return [{"type": "requirement", "text": "Contact the WMS key user.", "citations": cite}]

    fake.responder = _escalating(escalation=documented)
    card = workspace.card("The WMS shows the unknown error GR-299.", source_ids=[matrix]).json()["output"][
        "card"
    ]
    assert card["status"] == "expert_confirmation"
    assert card["fallback_escalation"] is None


def test_rck_05_a_missing_workspace_is_set_up_by_a_post_not_a_page_load(visitor, db):
    """Full audit re-check RCK-05: pages never write. When the visitor has no copy of the
    governed workspace, the page offers a CSRF-checked button that makes one."""
    count = "SELECT COUNT(*) FROM notebook WHERE kind = 'ops_workspace'"
    db.execute("DELETE FROM notebook WHERE kind = 'ops_workspace'")
    db.commit()
    page = visitor.client.get("/app")
    assert page.status_code == 200 and "Set up the Inbound Operations demo" in page.text
    assert db.execute(count).fetchone()[0] == 0, "the page load wrote nothing"
    assert visitor.client.post("/workspace/reset").status_code == 403, "no token, no copy"
    made = visitor.client.post("/workspace/reset", headers=visitor.json_headers())
    assert made.status_code == 200 and db.execute(count).fetchone()[0] == 1
