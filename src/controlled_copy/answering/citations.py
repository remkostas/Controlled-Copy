"""Turn model statements into verified statements with numbered citations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from controlled_copy.answering.prompts import passage_label
from controlled_copy.answering.verify import find_quote
from controlled_copy.retrieval.search import Passage


class CitationOut(BaseModel):
    passage_id: str = Field(max_length=20)
    quote: str = Field(max_length=2000)


class StatementOut(BaseModel):
    text: str = Field(max_length=4000)
    citations: list[CitationOut] = Field(max_length=10)
    type: str | None = None


def short_locator(locator: str) -> str:
    return locator.split(" › ")[-1]


def located_label(document: str, locator: str) -> str:
    """'SOP-INB-001 rev 3 · 4.2 Quantity check': the label on chips and in the viewer."""
    return f"{document} · {short_locator(locator)}"


def citation_label(passage: Passage) -> str:
    return located_label(passage_label(passage), passage.locator)


@dataclass
class CitationNumbering:
    """Numbers each distinct quoted span once per answer or output, in order of appearance."""

    numbers: dict[tuple[int, int, int], int] = field(default_factory=dict)
    flat: list[dict[str, Any]] = field(default_factory=list)

    def cite(self, passage: Passage, start: int, end: int, source_text: str) -> dict[str, Any]:
        key = (passage.chunk_id, start, end)
        if key not in self.numbers:
            self.numbers[key] = len(self.numbers) + 1
            self.flat.append(
                {
                    "n": self.numbers[key],
                    "source_id": passage.source_id,
                    "chunk_id": passage.chunk_id,
                    "start": start,
                    "end": end,
                    "label": citation_label(passage),
                    "quote": source_text,
                }
            )
        return next(c for c in self.flat if c["n"] == self.numbers[key])


@dataclass
class VerifiedStatements:
    statements: list[dict[str, Any]]
    removed: int
    removed_citations: int


def verify_statements(
    raw: Sequence[StatementOut],
    mapping: dict[str, Passage],
    numbering: CitationNumbering,
) -> VerifiedStatements:
    """Keep statements that have at least one verified citation.

    A citation is verified when its passage ID was in the prompt and its quote
    occurs in that passage. Offsets are stored relative to the source text.
    """
    kept: list[dict[str, Any]] = []
    removed = 0
    removed_citations = 0
    for statement in raw:
        cites: list[dict[str, Any]] = []
        for citation in statement.citations:
            passage = mapping.get(citation.passage_id.strip())
            match = find_quote(passage.text, citation.quote) if passage else None
            if passage is None or match is None:
                removed_citations += 1
                continue
            start = passage.char_start + match.start
            end = passage.char_start + match.end
            entry = numbering.cite(passage, start, end, passage.text[match.start : match.end])
            if entry not in cites:
                cites.append(entry)
        text = " ".join(statement.text.split())
        if cites and text:
            item: dict[str, Any] = {"text": text, "cites": [{"n": c["n"]} for c in cites]}
            if statement.type is not None:
                item["type"] = statement.type
            kept.append(item)
        else:
            removed += 1
    return VerifiedStatements(kept, removed, removed_citations)
