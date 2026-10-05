"""Deterministic document-control rules. No model is involved in any of these decisions.

- Which documents are authoritative for a context (site, role, date), and why the
  others are excluded.
- Which identifiers a situation mentions and whether any source documents them.
- Which statement types survive verification, and which result status a card gets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# Error codes and document IDs (GR-204, SOP-INB-001) and location codes (A-14, OD-01, Q-01).
IDENTIFIER = re.compile(r"\b(?:[A-Z]{2,}(?:-[A-Z0-9]+)*-\d{2,}|[A-Z]{1,3}-\d{2,3})\b")

STATUS_PRECEDENCE = ("conflict", "expert_confirmation", "context_incomplete", "supported")
STATUS_LABELS = {
    "conflict": "Conflicting instructions",
    "expert_confirmation": "Expert confirmation required",
    "context_incomplete": "Context incomplete",
    "supported": "Supported by an approved instruction",
    "refusal": "Not in the selected sources",
}
TYPES = ("requirement", "inference", "recommendation", "missing_evidence")


@dataclass(frozen=True)
class Context:
    site: str
    role: str
    as_of: date


@dataclass(frozen=True)
class Document:
    source_id: str
    title: str
    document_id: str | None
    revision: str | None
    status: str
    effective_from: date | None
    site: str | None
    roles: tuple[str, ...]
    origin: str

    @property
    def label(self) -> str:
        if self.document_id:
            return f"{self.document_id} rev {self.revision}" if self.revision else self.document_id
        return self.title

    @property
    def revision_number(self) -> float:
        try:
            return float(self.revision or 0)
        except ValueError:
            return 0.0


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def document_from(source_id: str, title: str, metadata: dict[str, Any] | None, origin: str) -> Document:
    meta = metadata or {}
    roles = meta.get("applicable_roles") or []
    return Document(
        source_id=source_id,
        title=title,
        document_id=meta.get("document_id"),
        revision=meta.get("revision"),
        status=meta.get("status") or "unknown",
        effective_from=_parse_date(meta.get("effective_from")),
        site=meta.get("site"),
        roles=tuple(str(r) for r in roles),
        origin=origin if meta else "none",
    )


@dataclass
class Split:
    authoritative: list[Document] = field(default_factory=list)
    excluded: dict[str, tuple[Document, str]] = field(default_factory=dict)

    def authoritative_ids(self) -> list[str]:
        return [d.source_id for d in self.authoritative]

    def excluded_ids(self) -> list[str]:
        return list(self.excluded)

    def document(self, source_id: str) -> Document | None:
        for doc in self.authoritative:
            if doc.source_id == source_id:
                return doc
        entry = self.excluded.get(source_id)
        return entry[0] if entry else None


def split(documents: Sequence[Document], context: Context) -> Split:
    """Authoritative: approved, effective on the date, matching site and role, not superseded."""
    result = Split()
    candidates: list[Document] = []
    for doc in documents:
        reason = _exclusion_reason(doc, context)
        if reason:
            result.excluded[doc.source_id] = (doc, reason)
        else:
            candidates.append(doc)
    for doc in candidates:
        newer = [
            other
            for other in candidates
            if other.document_id
            and other.document_id == doc.document_id
            and other.revision_number > doc.revision_number
        ]
        if newer:
            best = max(newer, key=lambda other: other.revision_number)
            result.excluded[doc.source_id] = (doc, f"superseded by {best.label}")
        else:
            result.authoritative.append(doc)
    return result


def _exclusion_reason(doc: Document, context: Context) -> str | None:
    if doc.origin == "none" or doc.status == "unknown":
        return "status unknown: no document-control metadata"
    if doc.status == "obsolete":
        return "obsolete"
    if doc.status == "draft":
        when = f", effective from {doc.effective_from.isoformat()}" if doc.effective_from else ""
        return f"draft, not approved{when}"
    if doc.status != "approved":
        return f"status {doc.status}"
    if doc.effective_from is None:
        return "no effective date"
    if doc.effective_from > context.as_of:
        return f"not yet effective (from {doc.effective_from.isoformat()})"
    if doc.site and doc.site.lower() != "all" and doc.site != context.site:
        return f"other site ({doc.site})"
    if doc.roles and context.role not in doc.roles:
        return f"not for role {context.role}"
    return None


def identifiers(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0) for match in IDENTIFIER.finditer(text)))


def documented_in(identifier: str, texts: dict[str, str]) -> list[str]:
    """Source IDs whose text contains the identifier as a whole token."""
    pattern = re.compile(rf"(?<![A-Za-z0-9-]){re.escape(identifier)}(?![A-Za-z0-9])")
    return [source_id for source_id, text in texts.items() if pattern.search(text)]


def apply_type_rules(
    item: dict[str, Any], cited_sources: Iterable[str], authoritative: set[str]
) -> dict[str, Any] | None:
    """Enforce statement types after quote verification. Returns the item to show, or None.

    - requirement: needs a verified quote from an authoritative document; otherwise it is
      downgraded to inference (verified quote from elsewhere) or missing evidence (none).
    - inference: needs at least one verified quote, otherwise it is dropped.
    - recommendation and missing evidence: shown with their label, citations optional.
    """
    kind = item.get("type") if item.get("type") in TYPES else "inference"
    cited = set(cited_sources)
    shown = dict(item)
    if kind == "requirement":
        if cited & authoritative:
            shown["type"] = "requirement"
        elif cited:
            shown["type"] = "inference"
            shown["downgraded"] = "quote not from an applicable approved document"
        else:
            shown["type"] = "missing_evidence"
            shown["downgraded"] = "no verified quote in an applicable approved document"
        return shown
    if kind == "inference":
        return {**shown, "type": "inference"} if cited else None
    return {**shown, "type": kind}


def result_status(
    *,
    conflict: bool,
    undocumented: Sequence[str],
    authoritative_evidence: int,
    only_unknown_sources: bool,
    missing: int,
) -> tuple[str, list[str]]:
    """One primary status by precedence, with the reasons that produced it."""
    reasons: list[str] = []
    if conflict:
        reasons.append("two applicable approved documents give different instructions")
        return "conflict", reasons
    if undocumented:
        reasons.append("no applicable approved document covers " + ", ".join(undocumented))
    if only_unknown_sources:
        reasons.append("only sources without document-control metadata match")
    if authoritative_evidence == 0:
        reasons.append("no applicable approved instruction was found")
    if reasons:
        return "expert_confirmation", reasons
    if missing:
        return "context_incomplete", [f"{missing} piece{'s' if missing != 1 else ''} of information missing"]
    return "supported", ["every required action is backed by an applicable approved instruction"]
