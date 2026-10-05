"""Hybrid retrieval over the selected sources.

Full-text search (SQLite FTS5, BM25) finds exact terms such as error codes;
vector search (exact cosine over stored embeddings) finds paraphrases. Both
ranked lists are fused with reciprocal rank fusion (RRF). The evidence floor
decides, before any generation call, whether the best match is strong enough
to answer at all.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from controlled_copy.ingestion.pipeline import embed_texts
from controlled_copy.services import Services

RRF_K = 60
TOKEN = re.compile(r"[A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)*")
IDENTIFIER = re.compile(r"\b[A-Za-z]{2,}(?:-[A-Za-z0-9]+)*-[A-Za-z0-9]*\d[A-Za-z0-9]*\b")
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "doing",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "should",
        "so",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "too",
        "very",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
        "about",
        "any",
        "all",
        "also",
        "am",
        "may",
        "might",
        "must",
        "shall",
    ]
)


@dataclass(frozen=True)
class Passage:
    chunk_id: int
    source_id: str
    source_title: str
    source_kind: str
    locator: str
    page: int | None
    char_start: int
    char_end: int
    text: str
    metadata: dict[str, Any] | None
    metadata_origin: str
    cosine: float
    fused: float

    @classmethod
    def from_row(cls, row: Any, cosine: float = 0.0, fused: float = 0.0) -> Passage:
        """From a chunk row joined with its source (Repo.chunks_by_ids / chunks_for_sources)."""
        return cls(
            chunk_id=int(row["id"]),
            source_id=row["source_id"],
            source_title=row["source_title"],
            source_kind=row["source_kind"],
            locator=row["locator"],
            page=row["page"],
            char_start=row["char_start"],
            char_end=row["char_end"],
            text=row["text"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else None,
            metadata_origin=row["metadata_origin"],
            cosine=cosine,
            fused=fused,
        )


@dataclass
class RetrievalResult:
    query: str
    passages: list[Passage]
    best_cosine: float
    identifiers: list[str] = field(default_factory=list)
    exact_identifier_hit: bool = False
    fts_hits: int = 0

    def above_floor(self, floor: float) -> bool:
        return bool(self.passages) and (self.best_cosine >= floor or self.exact_identifier_hit)


def fts_query(text: str) -> str:
    """Turn free text into a safe FTS5 query: quoted terms joined by OR."""
    terms: list[str] = []
    for token in TOKEN.findall(text):
        parts = [p for p in re.split(r"[-_./]", token.lower()) if p]
        if len(parts) == 1 and (parts[0] in STOPWORDS or (len(parts[0]) < 2 and not parts[0].isdigit())):
            continue
        phrase = " ".join(parts)
        quoted = '"' + phrase.replace('"', "") + '"'
        if quoted not in terms:
            terms.append(quoted)
    return " OR ".join(terms[:40])


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def extract_identifiers(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(0).upper() for match in IDENTIFIER.finditer(text)))


def embed_query(services: Services, query: str) -> np.ndarray:
    return np.asarray(embed_texts(services, [query], kind="embed_query")[0], dtype=np.float32)


def retrieve(
    services: Services,
    source_ids: list[str],
    query: str,
    top_k: int | None = None,
    query_vector: np.ndarray | None = None,
) -> RetrievalResult:
    """Hybrid search; pass `query_vector` to reuse one query embedding across several searches."""
    settings = services.settings
    top_k = top_k or settings.retrieval_top_k
    candidates = settings.retrieval_candidates
    repo = services.repo

    fts_ids = repo.fts_search(source_ids, fts_query(query), candidates)

    vector_ids: list[int] = []
    cosines: dict[int, float] = {}
    chunk_ids, matrix = repo.vectors_for_sources(source_ids, settings.model_embedding)
    if chunk_ids:
        if query_vector is None:
            query_vector = embed_query(services, query)
        norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(query_vector) or 1.0)
        norms[norms == 0] = 1.0
        scores = (matrix @ query_vector) / norms
        order = np.argsort(-scores)[:candidates]
        vector_ids = [chunk_ids[i] for i in order]
        cosines = {chunk_ids[i]: float(scores[i]) for i in range(len(chunk_ids))}

    fused = rrf([fts_ids, vector_ids])[:top_k]
    rows = repo.chunks_by_ids([chunk_id for chunk_id, _ in fused])
    passages = [
        Passage.from_row(rows[chunk_id], cosines.get(chunk_id, 0.0), score)
        for chunk_id, score in fused
        if chunk_id in rows
    ]
    identifiers = extract_identifiers(query)
    exact = any(ident.lower() in p.text.lower() for ident in identifiers for p in passages)
    return RetrievalResult(
        query=query,
        passages=passages,
        best_cosine=max(cosines.values(), default=0.0),
        identifiers=identifiers,
        exact_identifier_hit=exact,
        fts_hits=len(fts_ids),
    )
