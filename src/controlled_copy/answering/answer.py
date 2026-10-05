"""Answer a question (or follow-up) from the selected sources of a notebook."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from controlled_copy.answering import prompts
from controlled_copy.answering.citations import CitationNumbering, StatementOut, verify_statements
from controlled_copy.answering.generate import GenerationError, generate
from controlled_copy.limits import DAILY_LIMIT_MESSAGE, LimitExceeded
from controlled_copy.logs import log_event
from controlled_copy.providers.base import ProviderError
from controlled_copy.retrieval.search import retrieve
from controlled_copy.services import Services
from controlled_copy.storage.repo import TOMBSTONE, OwnedNotebook


class AnswerOut(BaseModel):
    statements: list[StatementOut] = Field(max_length=20)
    unanswerable: list[str] = Field(max_length=10)


class RewriteOut(BaseModel):
    search_question: str = Field(max_length=2000)


class AskError(Exception):
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class TurnResult:
    turn_id: str
    question: str
    search_query: str | None
    answer: dict[str, Any]
    citations: list[dict[str, Any]]


def history_pairs(messages: list[sqlite3.Row], limit: int = 2) -> list[tuple[str, str]]:
    """The last `limit` completed turns as (question, answer text) pairs."""
    return [(question, text) for question, text, _ in history_turns(messages, limit)]


def history_turns(messages: list[sqlite3.Row], limit: int = 2) -> list[tuple[str, str, set[str]]]:
    """The last `limit` completed turns: question, answer text and the sources behind them."""
    turns: dict[str, dict[str, Any]] = {}
    for row in messages:
        turns.setdefault(row["turn_id"], {})[row["role"]] = row
    pairs: list[tuple[str, str, set[str]]] = []
    for turn in turns.values():
        user, assistant = turn.get("user"), turn.get("assistant")
        if not user or not assistant or assistant["status"] == TOMBSTONE:
            continue
        answer = json.loads(assistant["content"] or "{}")
        if answer.get("kind") == "answer":
            text = " ".join(s["text"] for s in answer.get("statements", []))
        else:
            text = "(not answered from the sources)"
        sources = {
            c["source_id"] for c in json.loads(assistant["citations_json"] or "[]") if c.get("source_id")
        }
        pairs.append((user["content"], text, sources))
    return pairs[-limit:]


def rewrite_question(services: Services, history: list[tuple[str, str]], question: str) -> str:
    payload, _ = generate(
        services,
        prompts.rewrite_messages(history, question),
        schema=prompts.REWRITE_SCHEMA,
        schema_name="rewrite",
        model_cls=RewriteOut,
    )
    rewritten = " ".join(payload.search_question.split())[: services.settings.max_question_chars]
    return rewritten or question


def _same_question(first: str, second: str) -> bool:
    return " ".join(first.lower().split()).rstrip("?.! ") == " ".join(second.lower().split()).rstrip("?.! ")


def ask(services: Services, notebook: OwnedNotebook, question: str, selected_ids: list[str]) -> TurnResult:
    settings = services.settings
    repo = services.repo
    question = question.strip()
    if not question:
        raise AskError("Type a question first.", 422)
    if len(question) > settings.max_question_chars:
        raise AskError(f"Questions are limited to {settings.max_question_chars:,} characters.", 422)
    sources = repo.sources_by_ids(notebook, selected_ids)
    if not sources:
        raise AskError("Select at least one source to ask about.", 422)
    if services.budget.read_only():
        raise AskError(DAILY_LIMIT_MESSAGE, 503)
    source_ids = [row["id"] for row in sources]

    try:
        turns = history_turns(repo.list_messages(notebook))
        history = [(q, text) for q, text, _ in turns]
        # Every source behind this turn: the selection, and the history a rewrite draws on.
        lineage = set(source_ids) | {s for _, _, sources in turns for s in sources}
        search_query: str | None = None
        if history:
            rewritten = rewrite_question(services, history, question)
            # Only show (and use) a rewrite that actually changed the question.
            search_query = None if _same_question(rewritten, question) else rewritten
        query = search_query or question
        retrieval = retrieve(services, source_ids, query)
        if not retrieval.above_floor(settings.evidence_floor):
            answer = refusal(len(source_ids), query, None)
            log_event(
                "answer",
                session=services.session_id,
                notebook=notebook.id,
                outcome="refused_floor",
                best_cosine=round(retrieval.best_cosine, 3),
                passages=len(retrieval.passages),
            )
            return _store(services, notebook, question, search_query, answer, [], sorted(lineage))

        messages, mapping = prompts.answer_messages(search_query or question, retrieval.passages)
        payload, result = generate(
            services, messages, schema=prompts.ANSWER_SCHEMA, schema_name="answer", model_cls=AnswerOut
        )
    except (GenerationError, LimitExceeded) as exc:
        raise AskError(exc.message, exc.status) from exc
    except ProviderError as exc:
        raise AskError(
            "The model provider is not available right now. Please try again in a minute.", 502
        ) from exc

    numbering = CitationNumbering()
    verified = verify_statements(payload.statements, mapping, numbering)
    gaps = [" ".join(g.split())[:300] for g in payload.unanswerable if g.strip()][:5]
    if verified.statements:
        answer = {
            "kind": "answer",
            "statements": verified.statements,
            "citations": numbering.flat,
            "gaps": gaps,
            "removed": verified.removed,
            "searched_sources": len(source_ids),
            "search_query": query,
            "model": result.model,
        }
    else:
        reason = gaps[0] if gaps else None
        answer = refusal(len(source_ids), query, reason)
        answer["removed"] = verified.removed
    log_event(
        "answer",
        session=services.session_id,
        notebook=notebook.id,
        outcome=answer["kind"],
        statements=len(verified.statements),
        removed=verified.removed,
        removed_citations=verified.removed_citations,
        best_cosine=round(retrieval.best_cosine, 3),
        model=result.model,
    )
    return _store(services, notebook, question, search_query, answer, numbering.flat, sorted(lineage))


def refusal(searched_sources: int, query: str, reason: str | None) -> dict[str, Any]:
    return {
        "kind": "refusal",
        "statements": [],
        "citations": [],
        "gaps": [],
        "removed": 0,
        "searched_sources": searched_sources,
        "search_query": query,
        "reason": reason,
    }


def _store(
    services: Services,
    notebook: OwnedNotebook,
    question: str,
    search_query: str | None,
    answer: dict[str, Any],
    citations: list[dict[str, Any]],
    context_source_ids: list[str],
) -> TurnResult:
    """Persist the turn. The stored source list covers every selected source and the sources
    behind the history used for a rewrite, so deleting any of them removes the turn (S-05)."""
    sources = sorted({c["source_id"] for c in citations} | set(context_source_ids))
    turn_id = services.repo.add_turn(
        notebook, question, answer, search_query, [{"source_id": s} for s in sources], "ok"
    )
    return TurnResult(turn_id, question, search_query, answer, citations)
