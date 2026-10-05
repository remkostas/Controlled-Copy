"""Studio actions of the core: the Briefing and the suggested questions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel, Field

from controlled_copy.answering import prompts
from controlled_copy.answering.generate import GenerationError, generate
from controlled_copy.limits import DAILY_LIMIT_MESSAGE, LimitExceeded
from controlled_copy.logs import log_event
from controlled_copy.providers.base import ProviderError
from controlled_copy.services import Services
from controlled_copy.storage.repo import OwnedNotebook
from controlled_copy.studio.engine import StudioTemplate, run_template, select_overview_passages


class StudioError(Exception):
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


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
    try:
        result = run_template(services, template, passages)
    except (GenerationError, LimitExceeded) as exc:
        raise StudioError(exc.message, exc.status) from exc
    except ProviderError as exc:
        raise StudioError(
            "The model provider is not available right now. Please try again in a minute.", 502
        ) from exc
    output = result.output
    output["source_count"] = len(source_ids)
    # Every selected source fed the prompt, so deleting any of them removes this output.
    flat = [{"source_id": source_id} for source_id in source_ids]
    output_id = services.repo.add_output(notebook, template.id, None, output, flat, "ok")
    log_event(
        "studio_output",
        session=services.session_id,
        notebook=notebook.id,
        output=output_id,
        template=template.id,
        items=sum(len(s["items"]) for s in output["sections"]),
        removed=output["removed"],
        model=result.model,
    )
    return StoredOutput(output_id, output)


class SuggestOut(BaseModel):
    questions: list[str] = Field(max_length=10)


def suggestions_key(source_ids: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(source_ids)).encode()).hexdigest()[:24]


def suggested_questions(services: Services, notebook: OwnedNotebook) -> list[str]:
    """Three questions about the notebook's sources, generated once per change of sources."""
    sources = services.repo.list_sources(notebook)
    if not sources:
        return []
    source_ids = [row["id"] for row in sources]
    key = suggestions_key(source_ids)
    if notebook["suggestions_key"] == key and notebook["suggestions_json"]:
        return json.loads(notebook["suggestions_json"])
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
    except (GenerationError, LimitExceeded, ProviderError):
        return []
    questions = []
    for question in payload.questions:
        cleaned = " ".join(question.split())[:160]
        if cleaned and cleaned not in questions:
            questions.append(cleaned)
    questions = questions[:3]
    services.repo.set_suggestions(notebook, key, questions, source_ids)
    return questions
