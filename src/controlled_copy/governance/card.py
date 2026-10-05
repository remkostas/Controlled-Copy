"""The Resolution Card: what applicable approved instructions say about a situation.

Pipeline: identifiers by pattern, authoritative and excluded split by rules, retrieval
within the authoritative set (and separately within the excluded set, only to raise
warnings), one structured model call on authoritative passages only, quote
verification, statement-type rules and a status chosen by precedence. The model
never decides which document applies, and never decides the status.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

from controlled_copy.errors import PROVIDER_UNAVAILABLE
from controlled_copy.governance import rules
from controlled_copy.limits import DAILY_LIMIT_MESSAGE
from controlled_copy.logs import log_event
from controlled_copy.providers.base import ProviderError
from controlled_copy.retrieval.search import Passage, RetrievalResult, embed_query, retrieve
from controlled_copy.services import Services
from controlled_copy.storage.repo import OwnedNotebook
from controlled_copy.studio.actions import StoredOutput, StudioError
from controlled_copy.studio.engine import StudioTemplate, load_template, run_template

TEMPLATE_ID = "resolution-card"
MAX_WARNINGS = 3
MAX_REFERENCED = 2


@cache
def card_template() -> StudioTemplate:
    return load_template(Path(__file__).parent / "templates" / f"{TEMPLATE_ID}.json")


@dataclass(frozen=True)
class CardInput:
    situation: str
    context: rules.Context


def documents_of(rows: list[Any]) -> list[rules.Document]:
    return [
        rules.document_from(
            row["id"],
            row["title"],
            json.loads(row["metadata_json"]) if row["metadata_json"] else None,
            row["metadata_origin"],
        )
        for row in rows
    ]


def context_options(rows: list[Any]) -> dict[str, list[str]]:
    sites: set[str] = set()
    roles: set[str] = set()
    for doc in documents_of(rows):
        if doc.site and doc.site.lower() != "all":
            sites.add(doc.site)
        roles.update(doc.roles)
    return {"sites": sorted(sites), "roles": sorted(roles)}


def _warnings(
    result: RetrievalResult, split: rules.Split, identifiers: list[str], floor: float
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for passage in result.passages:
        if passage.source_id in seen or passage.source_id not in split.excluded:
            continue
        has_identifier = any(i in passage.text for i in identifiers)
        if passage.cosine < floor and not has_identifier:
            continue
        seen.add(passage.source_id)
        doc, reason = split.excluded[passage.source_id]
        excerpt = " ".join(passage.text.split())
        warnings.append(
            {
                "source_id": passage.source_id,
                "label": doc.label,
                "reason": reason,
                "locator": passage.locator.split(" › ")[-1],
                "excerpt": excerpt[:280] + ("…" if len(excerpt) > 280 else ""),
                "start": passage.char_start,
                "end": passage.char_end,
            }
        )
        if len(warnings) == MAX_WARNINGS:
            break
    return warnings


def referenced_documents(split: rules.Split, passages: list[Passage]) -> list[str]:
    """Applicable documents that the evidence names by document ID ("follow GUIDE-WMS-003")
    but that retrieval did not return, in the order they are named."""
    by_document_id = {d.document_id: d.source_id for d in split.authoritative if d.document_id}
    present = {p.source_id for p in passages}
    found: list[str] = []
    for passage in passages:
        for identifier in rules.identifiers(passage.text):
            source_id = by_document_id.get(identifier)
            if source_id and source_id not in present and source_id not in found:
                found.append(source_id)
    return found[:MAX_REFERENCED]


def _task(card: CardInput, identifiers: list[str], undocumented: list[str]) -> str:
    ctx = card.context
    lines = [
        f"Situation: {card.situation}",
        f"Reader: role {ctx.role} at site {ctx.site}, date {ctx.as_of.isoformat()}.",
    ]
    if identifiers:
        lines.append("Identifiers in the situation: " + ", ".join(identifiers) + ".")
    if undocumented:
        lines.append(
            "No applicable approved document covers: "
            + ", ".join(undocumented)
            + ". Do not guess what they mean; say what to do when a code is not documented,"
            " if a passage says it."
        )
    return "\n".join(lines)


def run_card(
    services: Services, notebook: OwnedNotebook, card: CardInput, selected_ids: list[str]
) -> StoredOutput:
    settings = services.settings
    situation = card.situation.strip()
    if not situation:
        raise StudioError("Describe the situation first.", 422)
    if len(situation) > settings.max_situation_chars:
        raise StudioError(f"Situations are limited to {settings.max_situation_chars:,} characters.", 422)
    rows = services.repo.sources_by_ids(notebook, selected_ids, with_text=True)
    if not rows:
        raise StudioError("Select at least one source first.", 422)
    if services.budget.read_only():
        raise StudioError(DAILY_LIMIT_MESSAGE, 503)

    split = rules.split(documents_of(rows), card.context)
    texts = {row["id"]: row["text"] for row in rows}
    found = rules.identifiers(situation)
    authoritative_ids = set(split.authoritative_ids())
    not_covered = rules.undocumented(found, texts, split)

    try:
        vector = embed_query(services, situation)

        def search(ids: list[str], top_k: int | None = None) -> RetrievalResult:
            return retrieve(services, ids, situation, top_k, query_vector=vector)

        auth = search(split.authoritative_ids()) if authoritative_ids else None
        excl = search(split.excluded_ids()) if split.excluded else None
        floor = settings.evidence_floor
        auth_relevant = auth is not None and auth.above_floor(floor)
        excl_relevant = excl is not None and excl.above_floor(floor)
        warnings = _warnings(excl, split, found, floor) if excl else []
        if not auth_relevant and not excl_relevant and not found:
            return _store(services, notebook, card, rows, _refusal(card, split, rows), [], [])
        context_sources: list[str] = [w["source_id"] for w in warnings]
        if auth_relevant:
            assert auth is not None
            evidence = list(auth.passages)
            for source_id in referenced_documents(split, evidence):
                evidence += search([source_id], top_k=1).passages
            result = run_template(services, card_template(), evidence, task=_task(card, found, not_covered))
            output, citations = result.output, result.citations
            context_sources += [p.source_id for p in evidence]
        else:
            output = {
                "sections": [{"key": s.key, "title": s.title, "items": []} for s in card_template().sections]
            }
            output.update(citations=[], removed=0, model=None)
            citations = []
    except ProviderError as exc:  # from the query embeddings; generation errors are already user-facing
        raise StudioError(PROVIDER_UNAVAILABLE, 502) from exc

    source_of = {c["n"]: c["source_id"] for c in citations}
    downgraded = 0
    conflict = False
    evidence_items = 0
    missing = 0
    for section in output["sections"]:
        kept = []
        for item in section["items"]:
            cited = [source_of[c["n"]] for c in item.get("cites", []) if c["n"] in source_of]
            if section["key"] == "conflicts":
                documents = {
                    split.document(s).document_id
                    for s in cited
                    if s in authoritative_ids and split.document(s)
                }
                if len(documents) >= 2:
                    conflict = True
                    kept.append({**item, "type": "conflict"})
                else:
                    downgraded += 1
                continue
            shown = rules.apply_type_rules(item, cited, authoritative_ids)
            if shown is None:
                downgraded += 1
                continue
            downgraded += 1 if "downgraded" in shown else 0
            grounded = bool(set(cited) & authoritative_ids)
            evidence_items += 1 if grounded else 0
            # Missing information counts towards the status only when the model listed it as such
            # and cited the passage that needs it; a downgraded requirement does not count.
            listed = shown["type"] == "missing_evidence" and "downgraded" not in shown
            missing += 1 if listed and grounded else 0
            kept.append(shown)
        section["items"] = kept

    only_unknown = (
        not auth_relevant
        and bool(warnings)
        and all(w["reason"].startswith("status unknown") for w in warnings)
    )
    status, reasons = rules.result_status(
        conflict=conflict,
        undocumented=not_covered,
        authoritative_evidence=evidence_items,
        only_unknown_sources=only_unknown,
        missing=missing,
    )
    cited_ids = {c["source_id"] for c in citations}
    output["card"] = _card_block(card, split, rows, found, not_covered, warnings, status, reasons, cited_ids)
    output["downgraded"] = downgraded
    output.update(kind="ok", template=TEMPLATE_ID, title="Resolution Card", source_count=len(rows))
    log_event(
        "resolution_card",
        session=services.session_id,
        notebook=notebook.id,
        status=status,
        items=sum(len(s["items"]) for s in output["sections"]),
        downgraded=downgraded,
        warnings=len(warnings),
        removed=int(output.get("removed", 0)),
    )
    return _store(services, notebook, card, rows, output, citations, context_sources)


def _card_block(
    card: CardInput,
    split: rules.Split,
    rows: list[Any],
    found: list[str],
    not_covered: list[str],
    warnings: list[dict[str, Any]],
    status: str,
    reasons: list[str],
    cited_ids: set[str],
) -> dict[str, Any]:
    used = [
        {
            "source_id": d.source_id,
            "label": d.label,
            "title": d.title,
            "status": d.status,
            "effective": d.effective_from.isoformat() if d.effective_from else None,
            "site": d.site,
            "origin": d.origin,
        }
        for d in split.authoritative
        if d.source_id in cited_ids
    ]
    excluded = [
        {"source_id": d.source_id, "label": d.label, "title": d.title, "reason": reason, "origin": d.origin}
        for d, reason in split.excluded.values()
    ]
    return {
        "status": status,
        "status_label": rules.STATUS_LABELS[status],
        "reasons": reasons,
        "situation": card.situation.strip(),
        "context": {
            "site": card.context.site,
            "role": card.context.role,
            "as_of": card.context.as_of.isoformat(),
        },
        "identifiers": found,
        "undocumented": not_covered,
        "used": used,
        "excluded": excluded,
        "warnings": warnings,
    }


def _refusal(card: CardInput, split: rules.Split, rows: list[Any]) -> dict[str, Any]:
    output: dict[str, Any] = {
        "kind": "ok",
        "template": TEMPLATE_ID,
        "title": "Resolution Card",
        "sections": [],
        "citations": [],
        "removed": 0,
        "downgraded": 0,
        "source_count": len(rows),
        "model": None,
    }
    output["card"] = _card_block(
        card,
        split,
        rows,
        [],
        [],
        [],
        "refusal",
        ["no passage in the selected sources is close to this situation"],
        set(),
    )
    return output


def _store(
    services: Services,
    notebook: OwnedNotebook,
    card: CardInput,
    rows: list[Any],
    output: dict[str, Any],
    citations: list[dict[str, Any]],
    context_sources: list[str],
) -> StoredOutput:
    # Lineage: every selected source (they all fed the split, the warnings or the prompt).
    lineage = {row["id"] for row in rows} | {c["source_id"] for c in citations} | set(context_sources)
    output_id = services.repo.add_output(notebook, TEMPLATE_ID, card.situation.strip(), output, lineage, "ok")
    return StoredOutput(output_id, output)


def today() -> date:
    return date.today()
