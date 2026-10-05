"""Studio: outputs built from templates that are data, not code paths.

A template (JSON) names its sections, the instruction for each, optional
statement types and a passage budget. The engine turns it into a JSON schema
and a prompt, runs one structured model call and verifies every item exactly
like a chat answer. Layers such as the governed Resolution Card reuse
`run_template` with their own passages and post-processing.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model

from controlled_copy.answering import prompts
from controlled_copy.answering.citations import CitationNumbering, StatementOut, verify_statements
from controlled_copy.answering.generate import generate
from controlled_copy.retrieval.search import Passage
from controlled_copy.services import Services

TEMPLATE_DIR = Path(__file__).parent / "templates"


class SectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,40}$")
    title: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=600)
    max_items: int = Field(ge=1, le=12)


class StudioTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,40}$")
    title: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=160)
    icon: str = Field(min_length=1, max_length=40)
    system: str = Field(min_length=1, max_length=4000)
    statement_types: list[str] | None = None
    passage_budget_chars: int = Field(ge=1000, le=60000)
    sections: list[SectionSpec] = Field(min_length=1, max_length=12)

    def schema(self) -> dict[str, Any]:
        item = prompts.statement_schema(self.statement_types)
        return {
            "type": "object",
            "properties": {s.key: {"type": "array", "items": item} for s in self.sections},
            "required": [s.key for s in self.sections],
            "additionalProperties": False,
        }

    def output_model(self) -> type[BaseModel]:
        fields: dict[str, Any] = {s.key: (list[StatementOut], Field(max_length=20)) for s in self.sections}
        return create_model(f"{self.id.title().replace('-', '')}Output", **fields)

    def instructions(self) -> str:
        lines = [self.system, "", "Sections:"]
        lines += [
            f"- {s.key} ({s.title}): {s.instruction} At most {s.max_items} items." for s in self.sections
        ]
        if self.statement_types:
            lines.append("Give every item a type: " + ", ".join(self.statement_types) + ".")
        lines.append(prompts.DATA_RULE)
        return "\n".join(lines)


def load_template(path: Path) -> StudioTemplate:
    return StudioTemplate.model_validate(json.loads(path.read_text(encoding="utf-8")))


@cache
def core_templates() -> dict[str, StudioTemplate]:
    templates = [load_template(path) for path in sorted(TEMPLATE_DIR.glob("*.json"))]
    return {t.id: t for t in templates}


def select_overview_passages(
    services: Services, source_ids: Sequence[str], budget_chars: int
) -> list[Passage]:
    """Spread the passage budget evenly over the selected sources, in document order."""
    rows = services.repo.chunks_for_sources(list(source_ids))
    if not rows:
        return []
    by_source: dict[str, list[Any]] = {}
    for row in rows:
        by_source.setdefault(row["source_id"], []).append(row)
    sources = services.repo.source_rows(list(by_source))
    share = max(1500, budget_chars // len(by_source))
    chosen: list[Passage] = []
    for source_id, chunks in by_source.items():
        used = 0
        step = max(1, len(chunks) // max(1, share // 900))
        for row in chunks[::step]:
            if used + len(row["text"]) > share and used:
                break
            used += len(row["text"])
            source = sources[source_id]
            chosen.append(
                Passage(
                    chunk_id=int(row["id"]),
                    source_id=source_id,
                    source_title=source["title"],
                    source_kind=source["kind"],
                    locator=row["locator"],
                    page=row["page"],
                    char_start=row["char_start"],
                    char_end=row["char_end"],
                    text=row["text"],
                    metadata=json.loads(source["metadata_json"]) if source["metadata_json"] else None,
                    metadata_origin=source["metadata_origin"],
                    cosine=0.0,
                    fused=0.0,
                )
            )
    return chosen


@dataclass
class StudioResult:
    output: dict[str, Any]
    citations: list[dict[str, Any]]
    model: str


Postprocess = Callable[[dict[str, Any]], dict[str, Any]]


def run_template(
    services: Services,
    template: StudioTemplate,
    passages: Sequence[Passage],
    *,
    task: str | None = None,
    extra: dict[str, Any] | None = None,
) -> StudioResult:
    block, mapping = prompts.passages_block(passages)
    user = (f"Task: {task}\n\n" if task else "") + f"Passages:\n{block}"
    messages = [{"role": "system", "content": template.instructions()}, {"role": "user", "content": user}]
    payload, result = generate(
        services,
        messages,
        schema=template.schema(),
        schema_name=template.id.replace("-", "_"),
        model_cls=template.output_model(),
    )
    numbering = CitationNumbering()
    sections = []
    removed = 0
    for spec in template.sections:
        raw = getattr(payload, spec.key)[: spec.max_items]
        if template.statement_types:
            allowed = template.statement_types
            raw = [s if s.type in allowed else s.model_copy(update={"type": None}) for s in raw]
        verified = verify_statements(raw, mapping, numbering)
        removed += verified.removed
        sections.append({"key": spec.key, "title": spec.title, "items": verified.statements})
    output = {
        "kind": "ok",
        "template": template.id,
        "title": template.title,
        "sections": sections,
        "citations": numbering.flat,
        "removed": removed,
        "source_count": len({p.source_id for p in passages}),
        "model": result.model,
        **(extra or {}),
    }
    return StudioResult(output=output, citations=numbering.flat, model=result.model)
