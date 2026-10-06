"""The Resolution Card: what applicable approved instructions say about a situation.

Pipeline: identifiers by pattern, authoritative and excluded split by rules, retrieval
within the authoritative set (and separately within the excluded set, only to raise
warnings), one structured model call on authoritative passages only, quote
verification, statement-type rules and a status chosen by precedence.

What rules decide: which documents apply, which statements may count (a requirement
needs a verified quote from an applicable approved document, a conflict verified quotes
from two of them) and the order of the statuses. What stays the model's reading, gated
by those verified quotes: whether two cited passages really conflict, and whether
information is missing (the model may also leave a missing item out).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from controlled_copy.answering.citations import short_locator
from controlled_copy.errors import PROVIDER_UNAVAILABLE
from controlled_copy.governance import rules
from controlled_copy.governance.seed import WORKSPACE_KIND
from controlled_copy.limits import DAILY_LIMIT_MESSAGE
from controlled_copy.logs import log_event
from controlled_copy.providers.base import ProviderError
from controlled_copy.retrieval.search import Passage, RetrievalResult, embed_query, retrieve
from controlled_copy.services import Services
from controlled_copy.storage.repo import TOMBSTONE, OwnedNotebook
from controlled_copy.studio.actions import StoredOutput, StudioError
from controlled_copy.studio.engine import StudioTemplate, load_template, run_template

TEMPLATE_ID = "resolution-card"
MAX_WARNINGS = 3
MAX_REFERENCED = 2
# A role or party an escalation can name ("QA lead", "WMS key user", "EHS", "purchasing",
# "safety officer"). Who decides only counts when the same role is in the statement and in its
# verified quote, so it comes from the documents, not from the model (second re-check R2-GOV-01).
ROLE = re.compile(
    r"\b(?:[a-z]+ )?(?:lead|inspector|key user|owner|officer|manager|supervisor|coordinator)\b"
    r"|\behs\b|\bpurchasing\b",
    re.IGNORECASE,
)
# Shown when a card asks for expert confirmation but no applicable document names who
# decides (S-26). Fixed text, never model output, and labelled as such on the card.
FALLBACK_ESCALATION = (
    "Stop and ask the person responsible for these documents, or your supervisor, before acting."
)


REQUIRED_SECTIONS = {"required_actions", "missing_information", "escalation", "conflicts"}


@cache
def card_template() -> StudioTemplate:
    template = load_template(Path(__file__).parent / "templates" / f"{TEMPLATE_ID}.json")
    # The status rules read these section keys; a renamed section must fail here, not
    # silently turn conflicts into ordinary statements.
    missing = REQUIRED_SECTIONS - {s.key for s in template.sections}
    if missing:
        raise ValueError(f"resolution card template lacks sections: {sorted(missing)}")
    return template


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
    # Curated documents first, so uploads that match closely cannot crowd out the warning
    # about a curated draft or obsolete revision.
    passages = sorted(
        (p for p in result.passages if p.source_id in split.excluded),
        key=lambda p: split.excluded[p.source_id][0].origin != "curated",
    )
    for passage in passages:
        if passage.source_id in seen:
            continue
        has_identifier = any(rules.documented_in(i, {"p": passage.text}) for i in identifiers)
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
                "locator": short_locator(passage.locator),
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


def _task(
    card: CardInput,
    identifiers: list[str],
    undocumented: list[str],
    unselected_only: list[tuple[str, list[str]]] = (),
) -> str:
    """The model's task. `undocumented`: codes no applicable approved document of the notebook
    covers. `unselected_only`: codes that one does cover but that is not selected, with its
    labels; they are documented, only not in the evidence (second re-check R2-GOV-02)."""
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
    for code, labels in unselected_only:
        lines.append(
            f"{code} is covered by {', '.join(labels)}, which is not among the selected sources. Do not"
            f" say {code} is undocumented and do not state what it requires; say that this document"
            " must be selected or consulted before acting."
        )
    return "\n".join(lines)


def run_card(services: Services, notebook: OwnedNotebook, card: CardInput, rows: list[Any]) -> StoredOutput:
    """`rows`: the selected sources of `notebook`, with text (Repo.sources_by_ids)."""
    settings = services.settings
    situation = card.situation.strip()
    if not situation:
        raise StudioError("Describe the situation first.", 422)
    if len(situation) > settings.max_situation_chars:
        raise StudioError(f"Situations are limited to {settings.max_situation_chars:,} characters.", 422)
    if not rows:
        raise StudioError("Select at least one source first.", 422)
    if services.budget.read_only():
        raise StudioError(DAILY_LIMIT_MESSAGE, 503)

    # What applies is decided over the whole notebook; the selection only chooses evidence.
    # Deselecting a newer revision, a code guide or a curated document never changes the rules.
    all_rows = services.repo.sources_by_ids(
        notebook, [row["id"] for row in services.repo.list_sources(notebook)], with_text=True
    )
    whole = rules.split(documents_of(all_rows), card.context, curated_only=notebook.kind == WORKSPACE_KIND)
    split = whole.restricted_to(row["id"] for row in rows)
    selected = {row["id"] for row in rows}
    not_selected = [d for d in whole.authoritative if d.source_id not in selected]
    texts = {row["id"]: row["text"] for row in all_rows}
    found = rules.identifiers(situation)
    authoritative_ids = set(split.authoritative_ids())
    # Undocumented means no applicable approved document of the notebook covers the code. A
    # code that only unselected ones cover is documented, but not in the evidence.
    not_covered = rules.undocumented(found, texts, whole)

    def covering(code: str) -> list[str]:
        return [d.label for d in not_selected if rules.documented_in(code, {d.source_id: texts[d.source_id]})]

    unselected_only = [
        (code, covering(code))
        for code in rules.undocumented(found, texts, whole, applicable=split.authoritative_ids())
        if code not in not_covered
    ]

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
            task = _task(card, found, not_covered, unselected_only)
            result = run_template(services, card_template(), evidence, task=task, keep_uncited=True)
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

    # Rules turn the model's verified items into counts; counts give the status.
    counts = rules.classify_items(output["sections"], {c["n"]: c["source_id"] for c in citations}, split)

    only_unknown = (
        not auth_relevant
        and bool(warnings)
        and all(w["reason"].startswith("status unknown") for w in warnings)
    )
    status, reasons = rules.result_status(
        conflict=counts.conflict,
        undocumented=not_covered,
        authoritative_evidence=counts.requirements,
        only_unknown_sources=only_unknown,
        missing=counts.missing,
        unverified=counts.unverified,
        asserted_only=counts.requirements > 0 and counts.curated_requirements == 0,
        unselected_only=unselected_only,
    )
    if status == "expert_confirmation" and counts.requirements == 0 and not_selected:
        labels = ", ".join(d.label for d in not_selected)
        reasons.append(f"applicable approved documents not selected: {labels}")
    cited_ids = {c["source_id"] for c in citations}
    output["card"] = _card_block(card, split, rows, found, not_covered, warnings, status, reasons, cited_ids)
    output["card"]["not_selected"] = [{"source_id": d.source_id, "label": d.label} for d in not_selected]
    # The standard line is left out only when a verified requirement from an applicable approved
    # document names who decides: an uncited recommendation does not count (full audit re-check
    # RCK-07), nor a cited instruction that names nobody (second re-check R2-GOV-01).
    escalation = next((sec["items"] for sec in output["sections"] if sec["key"] == "escalation"), [])
    quotes = {c["n"]: c.get("quote", "") for c in citations}
    documented = any(item.get("type") == "requirement" and _names_role(item, quotes) for item in escalation)
    if status == "expert_confirmation" and not documented:
        output["card"]["fallback_escalation"] = FALLBACK_ESCALATION
    # Applicable documents whose passages reached the model without being cited, so a
    # passage that steered the wording is still listed, with its origin.
    output["card"]["consulted"] = [
        {"source_id": d.source_id, "label": d.label, "title": d.title, "origin": d.origin}
        for d in split.authoritative
        if d.source_id in set(context_sources) - cited_ids
    ]
    output["downgraded"] = counts.downgraded
    output["dropped"] = counts.dropped
    output.update(kind="ok", template=TEMPLATE_ID, title="Resolution Card", source_count=len(rows))
    log_event(
        "resolution_card",
        session=services.session_id,
        notebook=notebook.id,
        status=status,
        items=sum(len(s["items"]) for s in output["sections"]),
        downgraded=counts.downgraded,
        dropped=counts.dropped,
        warnings=len(warnings),
        removed=int(output.get("removed", 0)),
    )
    return _store(services, notebook, card, rows, output, citations, context_sources)


def _names_role(item: dict[str, Any], quotes: dict[int, str]) -> bool:
    """Whether the statement names a role that its own verified quotes name too."""
    named = {m.group(0).lower() for m in ROLE.finditer(item.get("text", ""))}
    quoted = " ".join(quotes.get(c["n"], "") for c in item.get("cites", [])).lower()
    return any(role in quoted for role in named)


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
        # Every card shape carries every field, refusals included (the HTML and Markdown
        # renderers read them all).
        "consulted": [],
        "not_selected": [],
        "fallback_escalation": None,
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
        "dropped": 0,
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
    stored = services.repo.add_output(notebook, TEMPLATE_ID, card.situation.strip(), output, lineage, "ok")
    if stored.status == TOMBSTONE:
        return StoredOutput(stored.id, {"kind": "tombstone"})  # a source was deleted meanwhile
    return StoredOutput(stored.id, output)
