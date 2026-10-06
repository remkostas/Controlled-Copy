"""Deterministic document-control rules. No model is involved in any of these decisions.

- Which documents are authoritative for a context (site, role, date), and why the
  others are excluded.
- Which identifiers a situation mentions and whether any source documents them.
- Which statement types survive verification, and which result status a card gets.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# Error codes and document IDs (GR-204, SOP-INB-001) and location codes (A-14, OD-01, Q-01).
IDENTIFIER = re.compile(r"\b(?:[A-Z]{2,}(?:-[A-Z0-9]+)*-\d{2,}|[A-Z]{1,3}-\d{2,3})\b", re.IGNORECASE)
REVISION_PART = re.compile(r"\d+|[A-Za-z]+")
REVISION_PREFIX = re.compile(r"^\s*(?:revision|rev|v)\.?\s*(?=\d)", re.IGNORECASE)
DASHES = re.compile(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]")
DEFAULT_ROLE = "warehouse_operator"

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
    def id_key(self) -> str | None:
        return document_key(self.document_id)

    @property
    def revision_key(self) -> tuple[tuple[int, int | str], ...]:
        return revision_key(self.revision)


def document_key(document_id: Any) -> str | None:
    """Compare document IDs as one code: 'sop-inb-001' and 'SOP\u2011INB\u2011001' are SOP-INB-001."""
    text = unicodedata.normalize("NFKC", str(document_id or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")  # zero-width characters
    key = DASHES.sub("-", text).strip().casefold()
    return key or None


def revision_key(revision: Any) -> tuple[tuple[int, int | str], ...]:
    """Order revisions part by part: numbers numerically ('1.10' after '1.9'), letters
    alphabetically ('B' after 'A'), a number before a letter in the same position."""
    parts = REVISION_PART.findall(REVISION_PREFIX.sub("", str(revision or "")))
    return tuple((0, int(p)) if p.isdigit() else (1, p.upper()) for p in parts)


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
    # Metadata an uploader asserts never overrides a curated controlled document, also
    # when no curated revision applies to this context (a draft, another site). Where the
    # selection holds curated documents (the Inbound Operations workspace), asserted
    # metadata is not authoritative at all (D-039); without any, it counts (D-036).
    curated = {d.id_key for d in documents if d.id_key and d.origin == "curated"}
    has_curated = any(d.origin == "curated" for d in documents)
    eligible = []
    for doc in candidates:
        if doc.origin != "curated" and doc.id_key in curated:
            reason = f"asserted by uploader, but {doc.document_id} is a curated controlled document"
            result.excluded[doc.source_id] = (doc, reason)
        elif doc.origin != "curated" and has_curated:
            reason = "asserted by uploader; only curated documents are controlled here"
            result.excluded[doc.source_id] = (doc, reason)
        else:
            eligible.append(doc)
    for doc in eligible:
        newer = [
            other
            for other in eligible
            if other.id_key and other.id_key == doc.id_key and other.revision_key > doc.revision_key
        ]
        if newer:
            best = max(newer, key=lambda other: other.revision_key)
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
    # A document without a site applies nowhere: an omitted field must not widen it to every site.
    site = (doc.site or "").strip()
    if not site:
        return "no site in document-control metadata"
    if site.lower() != "all" and site.upper() != context.site.upper():
        return f"other site ({site})"
    if doc.roles and context.role not in doc.roles:
        return f"not for role {context.role}"
    return None


def identifiers(text: str) -> list[str]:
    """Codes in the text, upper-cased ('gr-299' is GR-299), in order of first appearance."""
    return list(dict.fromkeys(match.group(0).upper() for match in IDENTIFIER.finditer(text)))


def documented_in(identifier: str, texts: dict[str, str]) -> list[str]:
    """Source IDs whose text contains the identifier as a whole token."""
    pattern = re.compile(rf"(?<![A-Za-z0-9-]){re.escape(identifier)}(?![A-Za-z0-9])", re.IGNORECASE)
    return [source_id for source_id, text in texts.items() if pattern.search(text)]


def family(identifier: str) -> str:
    """The code family: everything before the last part (GR-299 -> GR, SOP-INB-001 -> SOP-INB)."""
    return identifier.rsplit("-", 1)[0]


def undocumented(found: Sequence[str], texts: dict[str, str], result: Split) -> list[str]:
    """Identifiers that no applicable approved document covers, from a family that the
    controlled documents define. GR-299 counts when the documents list other GR- codes; a
    reference that only an uncontrolled upload uses (a delivery note number such as
    DN-55821) is not a code the documents are expected to define."""
    controlled = [d.source_id for d in result.authoritative] + [
        d.source_id for d, _ in result.excluded.values() if d.origin != "none"
    ]
    families = {family(i) for sid in controlled for i in identifiers(texts.get(sid, ""))}
    applicable = {sid: texts[sid] for sid in result.authoritative_ids() if sid in texts}
    return [i for i in found if family(i) in families and not documented_in(i, applicable)]


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
    unverified: int = 0,
    asserted_only: bool = False,
) -> tuple[str, list[str]]:
    """One primary status by precedence, with the reasons that produced it.

    `authoritative_evidence` counts requirements with a verified quote from an applicable
    approved document; `unverified` counts requirements shown as missing evidence because
    their quote did not verify; `asserted_only` says that every one of them rests on
    document-control metadata an uploader asserted, which the status then names."""
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
    asserted = (
        ["the approval of these documents is asserted by the uploader, not checked"] if asserted_only else []
    )
    if unverified:
        return "supported", [
            *asserted,
            "backed by an applicable approved instruction; "
            f"{unverified} statement{'s' if unverified != 1 else ''} without a verified quote "
            "marked as missing evidence",
        ]
    return "supported", [*asserted, "every required action is backed by an applicable approved instruction"]
