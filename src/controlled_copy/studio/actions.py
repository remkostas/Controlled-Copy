"""Studio actions of the core: the Briefing and the suggested questions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator

from controlled_copy.answering import prompts
from controlled_copy.answering.generate import generate
from controlled_copy.errors import UserFacingError
from controlled_copy.limits import DAILY_LIMIT_MESSAGE
from controlled_copy.logs import log_event
from controlled_copy.providers.base import ProviderError
from controlled_copy.services import Services
from controlled_copy.storage.repo import TOMBSTONE, OwnedNotebook
from controlled_copy.studio.engine import StudioTemplate, run_template, select_overview_passages


class StudioError(UserFacingError):
    """A Studio action that cannot run as requested."""


@dataclass
class StoredOutput:
    output_id: str
    output: dict


def run_overview_template(
    services: Services, notebook: OwnedNotebook, template: StudioTemplate, selected_ids: list[str]
) -> StoredOutput:
    sources = services.repo.sources_by_ids(notebook, selected_ids)
    if not sources:
        raise StudioError("Select at least one source first.", 422)
    if services.budget.read_only():
        raise StudioError(DAILY_LIMIT_MESSAGE, 503)
    source_ids = [row["id"] for row in sources]
    passages = select_overview_passages(services, source_ids, template.passage_budget_chars)
    result = run_template(services, template, passages)  # raises user-facing errors only
    output = result.output
    output["source_count"] = len(source_ids)
    # Every selected source fed the prompt, so deleting any of them removes this output.
    stored = services.repo.add_output(notebook, template.id, None, output, source_ids, "ok")
    output_id = stored.id
    if stored.status == TOMBSTONE:
        output = {"kind": "tombstone"}  # a source was deleted while it was generated
    log_event(
        "studio_output",
        session=services.session_id,
        notebook=notebook.id,
        output=output_id,
        template=template.id,
        items=sum(len(s["items"]) for s in output.get("sections", [])),
        removed=output.get("removed", 0),
        model=result.model,
    )
    return StoredOutput(output_id, output)


class SuggestOut(BaseModel):
    """Exactly three distinct, non-empty questions after normalisation (FR-STU-02). Anything
    else is malformed output: generate() retries with the fallback model, and a failed
    attempt is never cached."""

    questions: list[str] = Field(max_length=10)

    @field_validator("questions")
    @classmethod
    def three_distinct(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for question in value:
            text = " ".join(question.split())[:160]
            if text and text.casefold() not in {q.casefold() for q in cleaned}:
                cleaned.append(text)
        if len(cleaned) < 3:
            raise ValueError("fewer than three distinct questions")
        return cleaned[:3]


def suggestions_key(source_ids: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(source_ids)).encode()).hexdigest()[:24]


def suggested_questions(services: Services, notebook: OwnedNotebook) -> list[str]:
    """Three questions about the notebook's sources, generated once per change of sources."""
    sources = services.repo.list_sources(notebook)
    if not sources:
        return []
    source_ids = [row["id"] for row in sources]
    key = suggestions_key(source_ids)
    if notebook.suggestions_key == key and notebook.suggestions_json:
        return json.loads(notebook.suggestions_json)
    if services.budget.read_only():
        return []
    passages = select_overview_passages(services, source_ids, 6000)
    try:
        payload, _ = generate(
            services,
            prompts.suggestion_messages(passages),
            schema=prompts.SUGGEST_SCHEMA,
            schema_name="suggestions",
            model_cls=SuggestOut,
        )
    except (UserFacingError, ProviderError):
        return []
    questions = payload.questions  # already three distinct, cleaned questions
    if not services.repo.set_suggestions(notebook, key, questions, source_ids):
        return []  # the sources changed (or one was deleted) while the questions were generated
    return questions
