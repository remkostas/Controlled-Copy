"""Deterministic fake model provider for tests and local runs without a key.

Embeddings are feature-hashed bags of words, so texts that share words are
similar and unrelated texts are not. Chat responses come from a `responder`
function; the default one builds a plausible, correctly quoted JSON answer
from the passages in the prompt, so the whole pipeline runs end to end.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from controlled_copy.answering import prompts
from controlled_copy.providers.base import ChatResult, EmbedResult, ProviderError

DIM = 1024
WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "should",
        "so",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    ]
)


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def hash_embed(text: str, dim: int = DIM) -> list[float]:
    vector = [0.0] * dim
    for word in WORD.findall(text.lower()):
        if word in STOPWORDS:
            continue
        digest = hashlib.blake2b(_stem(word).encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


@dataclass
class FakeRequest:
    messages: list[dict[str, str]]
    schema_name: str
    model: str
    schema: dict[str, Any]

    @property
    def user(self) -> str:
        return self.messages[-1]["content"]

    def passages(self) -> list[tuple[str, str]]:
        return prompts.parse_passages(self.user)


def first_sentence(text: str, max_words: int = 18) -> str:
    body = "\n".join(
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith(("#", ">", "|"))
    )
    sentence = re.split(r"(?<=[.!?])\s", body.strip(), maxsplit=1)[0]
    words = sentence.split()
    return " ".join(words[:max_words])


def default_responder(request: FakeRequest) -> dict[str, Any]:
    passages = request.passages()
    if request.schema_name == "rewrite":
        earlier, latest = prompts.parse_rewrite(request.user)
        follow_up = latest.lower().startswith(("and ", "what about", "how about")) or len(latest.split()) <= 4
        return {"search_question": " ".join([*earlier, latest]) if follow_up else latest}
    if request.schema_name == "suggestions":
        return {
            "questions": [
                "What is the main purpose of these sources?",
                "Which responsibilities do the sources define?",
                "What should happen when something goes wrong?",
            ]
        }
    if request.schema_name == "answer":
        if not passages:
            return {"statements": [], "unanswerable": ["The passages do not cover the question."]}
        pid, text = passages[0]
        quote = first_sentence(text)
        return {
            "statements": [
                {"text": f"The source states: {quote}", "citations": [{"passage_id": pid, "quote": quote}]}
            ],
            "unanswerable": [],
        }
    # Studio templates: one quoted item per section, cycling through passages.
    sections = list(request.schema.get("properties", {}).keys())
    item_schema = request.schema["properties"][sections[0]]["items"]["properties"] if sections else {}
    output: dict[str, Any] = {}
    for index, key in enumerate(sections):
        if not passages:
            output[key] = []
            continue
        pid, text = passages[index % len(passages)]
        quote = first_sentence(text)
        item: dict[str, Any] = {
            "text": f"Summary point: {quote}",
            "citations": [{"passage_id": pid, "quote": quote}],
        }
        if "type" in item_schema:
            item["type"] = item_schema["type"]["enum"][0]
        output[key] = [item]
    return output


Responder = Callable[[FakeRequest], dict[str, Any] | str]


@dataclass
class FakeProvider:
    responder: Responder = default_responder
    delay_seconds: float = 0.0
    failing_models: set[str] = field(default_factory=set)
    cost_per_call: float | None = None  # USD reported per chat call (tests of the spend limit)
    name: str = "fake"
    chat_calls: list[FakeRequest] = field(default_factory=list)
    embed_calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def embed(self, texts: list[str], *, model: str) -> EmbedResult:
        with self._lock:
            self.embed_calls += 1
        return EmbedResult(
            vectors=[hash_embed(t) for t in texts], model=model, input_tokens=sum(len(t) // 4 for t in texts)
        )

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any],
        schema_name: str,
        model: str,
        timeout: float,
    ) -> ChatResult:
        request = FakeRequest(messages=messages, schema_name=schema_name, model=model, schema=schema)
        with self._lock:
            self.chat_calls.append(request)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        if model in self.failing_models:
            raise ProviderError("fake provider failure")
        result = self.responder(request)
        content = result if isinstance(result, str) else json.dumps(result)
        return ChatResult(
            content=content,
            model=model,
            input_tokens=len(messages[-1]["content"]) // 4,
            output_tokens=len(content) // 4,
            cost_usd=self.cost_per_call,
        )
