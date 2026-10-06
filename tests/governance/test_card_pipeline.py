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


def test_a_card_without_a_verified_requirement_is_not_supported(workspace, fake):
    def build(request):
        pid, quote = passage_with(
            request, "post only the open quantity after the shift lead has confirmed the count"
        )
        cite = [{"passage_id": pid, "quote": quote}]
        return empty_card(
            escalation=[{"type": "recommendation", "text": "Ask the shift lead.", "citations": cite}]
        )

    fake.responder = card_responder(build)
    card = workspace.card("The WMS shows error GR-204 after I scan the delivery.").json()["output"]["card"]
    assert card["status"] == "expert_confirmation"
    assert card["reasons"] == ["no applicable approved instruction was found"]


def test_conflict_between_documents_without_ids_counts(visitor, fake, settings):
    first = b"---\nstatus: approved\neffective_from: 2026-01-01\nsite: all\n---\n# Dock rule A\n\nRefuse every damaged pallet at the dock.\n"
    second = b"---\nstatus: approved\neffective_from: 2026-01-01\nsite: all\n---\n# Dock rule B\n\nAccept every damaged pallet at the dock.\n"
    visitor.upload("a.md", first)
    visitor.upload("b.md", second)

    def build(request):
        a, a_quote = passage_with(request, "Refuse every damaged pallet at the dock")
        b, b_quote = passage_with(request, "Accept every damaged pallet at the dock")
        return empty_card(
            conflicts=[
                {
                    "type": "requirement",
                    "text": "Rule A refuses, rule B accepts.",
                    "citations": [{"passage_id": a, "quote": a_quote}, {"passage_id": b, "quote": b_quote}],
                }
            ]
        )

    fake.responder = card_responder(build)
    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/studio/resolution-card",
        data={
            "situation": "A damaged pallet at the dock.",
            "site": "HAM-01",
            "role": "warehouse_operator",
            "as_of": "2026-10-07",
            "source_ids": visitor.sources,
        },
        headers={**visitor.headers, "Accept": "application/json"},
    )
    assert response.json()["output"]["card"]["status"] == "conflict"


def test_the_chosen_site_and_role_are_never_replaced(workspace, fake):
    # Deselect the only HAM-02 document: the selection then offers no HAM-02 option, yet a
    # HAM-02 reader must stay HAM-02 so that HAM-01 instructions are excluded, not applied.
    titles = dict(zip(workspace.source_ids, workspace.source_titles(), strict=True))
    selected = [sid for sid, title in titles.items() if not title.startswith("Storage Location Rules")]
    assert len(selected) == 7
    situation = "The WMS shows error GR-204 after I scan the delivery."
    card = workspace.card(situation, site="HAM-02", source_ids=selected).json()["output"]["card"]
    assert card["context"]["site"] == "HAM-02"
    excluded = {d["label"]: d["reason"] for d in card["excluded"]}
    assert excluded["SOP-INB-001 rev 3"] == "other site (HAM-01)"
    assert card["status"] != "supported"
    card = workspace.card(situation, role="forklift_driver", source_ids=selected).json()["output"]["card"]
    assert card["context"]["role"] == "forklift_driver", "a role no document lists is kept, not replaced"
    assert "not for role forklift_driver" in {d["reason"] for d in card["excluded"]}


def test_reset_removes_uploaded_files(workspace, settings):
    visitor = workspace.visitor
    visitor.upload("note.txt", b"A note about dock 3.", notebook_id=workspace.id)
    assert any(settings.uploads_dir.iterdir())
    response = visitor.client.post(
        "/workspace/reset", headers={**visitor.headers, "Accept": "application/json"}
    )
    assert response.status_code == 200
    assert list(settings.uploads_dir.iterdir()) == []


def test_reset_that_fails_halfway_keeps_the_old_copy_and_its_files(workspace, settings, monkeypatch):
    from controlled_copy.governance import seed

    visitor = workspace.visitor
    visitor.upload("note.txt", b"A note about dock 3.", notebook_id=workspace.id)
    real = seed._copy_corpus

    def crash(services, sid, vectors):
        real(services, sid, vectors)  # the new copy is half written ...
        raise RuntimeError("disk full")  # ... when the reset fails

    monkeypatch.setattr(seed, "_copy_corpus", crash)
    response = visitor.client.post("/workspace/reset", headers=visitor.json_headers())
    assert response.status_code == 502
    workspace.refresh()
    assert len(workspace.source_ids) == 9, "the old copy, with the upload, is untouched"
    assert any(settings.uploads_dir.iterdir()), "its uploaded file is still there"


def test_seeding_that_fails_halfway_leaves_no_partial_workspace(services, monkeypatch):
    from controlled_copy.governance import seed
    from controlled_copy.storage.repo import Repo

    sid = services.repo.create_session()
    calls = []
    real = Repo.insert_source

    def failing(self, new, limit=None):
        calls.append(new.title)
        if len(calls) == 3:
            raise RuntimeError("crash")
        return real(self, new, limit)

    monkeypatch.setattr(Repo, "insert_source", failing)
    with pytest.raises(RuntimeError):
        seed.seed_workspace(services, sid)
    assert seed.workspace_of(services, sid) is None, "a retry seeds a complete copy"


def test_reset_is_limited_per_visitor(settings):
    from fastapi.testclient import TestClient

    from controlled_copy.app import create_app
    from controlled_copy.providers.fake import FakeProvider
    from tests.conftest import Visitor
    from tests.governance.conftest import Workspace

    app = create_app(
        settings.model_copy(update={"resets_per_visitor_hour": 2}), FakeProvider(), run_purge=False
    )
    with TestClient(app) as client:
        visitor = Visitor(client).login()
        Workspace(visitor)
        codes = [
            client.post("/workspace/reset", headers=visitor.json_headers()).status_code for _ in range(3)
        ]
    assert codes == [200, 200, 429]


def test_a_blank_site_is_refused_when_the_documents_name_sites(workspace):
    response = workspace.card("The WMS shows error GR-204 after I scan the delivery.", site="")
    assert response.status_code == 422
    assert response.json()["error"] == "Choose a site first."


def test_card_template_must_keep_the_sections_the_status_reads(monkeypatch):
    from controlled_copy.studio import engine

    real = engine.load_template

    def renamed(path):
        template = real(path)
        sections = [
            s.model_copy(update={"key": "conflict"}) if s.key == "conflicts" else s for s in template.sections
        ]
        return template.model_copy(update={"sections": sections})

    monkeypatch.setattr(card_module, "load_template", renamed)
    card_module.card_template.cache_clear()
    try:
        with pytest.raises(ValueError, match="conflicts"):
            card_module.card_template()
    finally:
        card_module.card_template.cache_clear()


def test_curated_warnings_come_before_uploads_and_codes_match_as_tokens():
    curated = rules.document_from(
        "draft", "Draft", {"document_id": "STD-LAB-002", "revision": "5", "status": "draft"}, "curated"
    )
    uploads = [rules.document_from(f"u{i}", f"Upload {i}", None, "none") for i in range(3)]
    split = rules.split([*uploads, curated], rules.Context("HAM-01", "warehouse_operator", date(2026, 10, 7)))
    result = card_module.RetrievalResult(
        query="",
        passages=[passage(f"u{i}", "Damaged pallet GR-2040 at the dock.") for i in range(3)]
        + [passage("draft", "For gr-204 on a damaged pallet: photograph it.")],
        best_cosine=0.9,
    )
    warnings = card_module._warnings(result, split, ["GR-204"], floor=0.95)
    assert [w["source_id"] for w in warnings] == ["draft"], (
        "the curated draft is warned about (gr-204 matches GR-204); GR-2040 is not GR-204"
    )


def test_seeding_failures_back_off(monkeypatch, settings):
    from controlled_copy.governance import seed

    calls = []

    def failing(services, sid):
        calls.append(sid)
        raise RuntimeError("provider down")

    monkeypatch.setattr(seed, "seed_workspace", failing)
    monkeypatch.setattr(seed, "workspace_of", lambda services, sid: None)
    seeder = seed.WorkspaceSeeder()
    seeder(None, "s1")
    seeder(None, "s2")
    assert calls == ["s1"], "the second page load within a minute does not retry"
    seeder.failed_at -= seeder.retry_seconds
    seeder(None, "s3")
    assert calls == ["s1", "s3"]
