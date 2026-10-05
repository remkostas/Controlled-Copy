"""Scripted fake-model responders for tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from controlled_copy.providers.fake import FakeRequest, default_responder, first_sentence


def answer_with(build: Callable[[list[tuple[str, str]]], dict[str, Any]]) -> Callable[[FakeRequest], Any]:
    """Use `build(passages)` for answer calls and the default responder for everything else."""

    def responder(request: FakeRequest) -> Any:
        if request.schema_name == "answer":
            return build(request.passages())
        return default_responder(request)

    return responder


def quote_passage_containing(needle: str, text: str = "Supported statement.") -> Callable[[FakeRequest], Any]:
    def build(passages: list[tuple[str, str]]) -> dict[str, Any]:
        for pid, body in passages:
            if needle.lower() in body.lower():
                start = body.lower().index(needle.lower())
                return {
                    "statements": [
                        {
                            "text": text,
                            "citations": [{"passage_id": pid, "quote": body[start : start + len(needle)]}],
                        }
                    ],
                    "unanswerable": [],
                }
        return {"statements": [], "unanswerable": ["not found"]}

    return answer_with(build)


def all_quotes_invalid() -> Callable[[FakeRequest], Any]:
    def build(passages: list[tuple[str, str]]) -> dict[str, Any]:
        pid = passages[0][0] if passages else "P1"
        return {
            "statements": [
                {
                    "text": "Invented claim one.",
                    "citations": [{"passage_id": pid, "quote": "this sentence does not exist anywhere"}],
                },
                {
                    "text": "Invented claim two.",
                    "citations": [
                        {
                            "passage_id": "P99",
                            "quote": first_sentence(passages[0][1]) if passages else "x y z",
                        }
                    ],
                },
            ],
            "unanswerable": [],
        }

    return answer_with(build)
