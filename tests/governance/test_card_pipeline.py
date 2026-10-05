"""Resolution Card pipeline details: cross-references and what drives the status (stage 2)."""

from __future__ import annotations

from datetime import date

import pytest

from controlled_copy.governance import card as card_module
from controlled_copy.governance import rules
from controlled_copy.retrieval.search import Passage
from tests.helpers.cards import card_responder, empty_card, passage_with

pytestmark = [pytest.mark.integration, pytest.mark.stage2]


def passage(source_id: str, text: str) -> Passage:
    return Passage(
        chunk_id=1,
        source_id=source_id,
        source_title=source_id,
        source_kind="md",
        locator="",
        page=None,
        char_start=0,
        char_end=len(text),
        text=text,
        metadata=None,
        metadata_origin="curated",
        cosine=0.9,
        fused=0.0,
    )


def test_referenced_documents_are_applicable_ones_named_by_the_evidence():
    def document(source_id: str, document_id: str, **meta) -> rules.Document:
        base = {"document_id": document_id, "revision": "1", "status": "approved"}
        base.update(effective_from="2026-01-01", site="all", **meta)
        return rules.document_from(source_id, document_id, base, "curated")

    split = rules.split(
        [
            document("guide", "GUIDE-WMS-003"),
            document("matrix", "MATRIX-ESC-001"),
            document("draft", "STD-LAB-002", status="draft"),
        ],
        rules.Context(site="HAM-01", role="warehouse_operator", as_of=date(2026, 10, 7)),
    )
    evidence = [
        passage("guide", "If the code is not listed, contact the key user (see MATRIX-ESC-001, STD-LAB-002).")
    ]
    # The matrix is applicable and missing from the evidence; the draft is not applicable.
    assert card_module.referenced_documents(split, evidence) == ["matrix"]
    assert card_module.referenced_documents(split, [*evidence, passage("matrix", "table")]) == []


def test_unknown_code_card_includes_the_referenced_escalation_document(workspace, fake):
    seen: list[str] = []

    def build(request):
        seen.extend(text for _, text in request.passages())
        return empty_card()

    fake.responder = card_responder(build)
    workspace.card("The WMS shows error GR-299 after I scan the delivery. What should I do?")
    assert any("WMS key user" in text and "unknown error codes" in text for text in seen), (
        "the escalation matrix, named by the guide, reaches the prompt"
    )


def test_only_cited_listed_missing_information_makes_the_context_incomplete(workspace, fake):
    def build(request):
        pid, quote = passage_with(
            request, "post only the open quantity after the shift lead has confirmed the count"
        )
        return empty_card(
            required_actions=[
                {
                    "type": "requirement",
                    "text": "Post only the open quantity.",
                    "citations": [{"passage_id": pid, "quote": quote}],
                },
                {"type": "requirement", "text": "Unquoted rule.", "citations": []},
            ],
            missing_information=[
                {"type": "missing_evidence", "text": "An uncited question.", "citations": []}
            ],
        )

    fake.responder = card_responder(build)
    card = workspace.card("The WMS shows error GR-204 after I scan the delivery.").json()["output"]
    types = [i["type"] for s in card["sections"] for i in s["items"]]
    assert types.count("missing_evidence") == 2, "both are shown"
    assert card["card"]["status"] == "supported", (
        "neither a downgraded requirement nor an uncited question counts"
    )

    def cited(request):
        pid, quote = passage_with(
            request, "post only the open quantity after the shift lead has confirmed the count"
        )
        cite = [{"passage_id": pid, "quote": quote}]
        return empty_card(
            required_actions=[
                {"type": "requirement", "text": "Post only the open quantity.", "citations": cite}
            ],
            missing_information=[
                {"type": "missing_evidence", "text": "Has the count been confirmed?", "citations": cite}
            ],
        )

    fake.responder = card_responder(cited)
    card = workspace.card("The WMS shows error GR-204 after I scan the delivery.").json()["output"]["card"]
    assert card["status"] == "context_incomplete"


def test_a_card_embeds_the_situation_once(workspace, fake):
    calls = fake.embed_calls
    workspace.card("The WMS shows error GR-299 after I scan the delivery. What should I do?")
    assert fake.embed_calls - calls == 1
