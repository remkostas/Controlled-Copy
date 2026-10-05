"""The per-visitor "Inbound Operations" workspace, seeded from the curated corpus.

The corpus is embedded once per corpus version and embedding model; the vectors are
kept in `seed_vector`. Seeding a visitor's copy, and every Reset, copies chunks and
vectors from there, so neither makes an embedding call (TC-GOV-002).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

from controlled_copy.ingestion import pipeline
from controlled_copy.ingestion.frontmatter import split_front_matter
from controlled_copy.logs import log_event
from controlled_copy.services import Services
from controlled_copy.storage.db import transaction
from controlled_copy.storage.repo import CapacityReached, NewSource, OwnedNotebook

WORKSPACE_TITLE = "Inbound Operations"
WORKSPACE_KIND = "ops_workspace"


def demo_data_dir() -> Path:
    # src/controlled_copy/governance/seed.py -> repository (or image) root
    return Path(__file__).resolve().parents[3] / "demo-data"


@dataclass(frozen=True)
class SeedDocument:
    key: str
    extracted: pipeline.Extracted


@cache
def corpus() -> tuple[str, tuple[SeedDocument, ...]]:
    """The curated documents (parsed once) and a hash that changes when any file changes."""
    folder = demo_data_dir() / "inbound-operations"
    digest = hashlib.sha256()
    documents = []
    for path in sorted(folder.glob("*.md")):
        data = path.read_bytes()
        digest.update(path.name.encode() + b"\0" + data)
        extracted = pipeline.extract_upload(
            path.name, data, max_pages=150, timeout=30, memory_mb=512, title_limit=200
        )
        metadata, _, _ = split_front_matter(data.decode("utf-8"))
        extracted.metadata = metadata
        extracted.metadata_origin = "curated"
        documents.append(SeedDocument(path.name, extracted))
    return digest.hexdigest()[:16], tuple(documents)


@cache
def scenarios() -> list[dict[str, Any]]:
    path = demo_data_dir() / "scenarios.json"
    return json.loads(path.read_text(encoding="utf-8"))["scenarios"] if path.exists() else []


def seed_vectors(services: Services) -> dict[tuple[str, int], np.ndarray]:
    """Vectors for every corpus chunk under the current model, computing them once if needed.
    The one-off embedding cost is shared infrastructure, not charged to the visitor's hour."""
    services = replace(services, session_id=None)
    corpus_hash, documents = corpus()
    model = services.settings.model_embedding
    conn = services.repo.conn
    rows = conn.execute(
        "SELECT document_key, ordinal, vector FROM seed_vector WHERE corpus_hash = ? AND model = ?",
        (corpus_hash, model),
    ).fetchall()
    expected = sum(len(d.extracted.chunks) for d in documents)
    if len(rows) != expected:
        texts = [
            pipeline.embedding_input(d.extracted.title, c) for d in documents for c in d.extracted.chunks
        ]
        vectors = pipeline.embed_texts(services, texts, kind="embed_seed")
        keys = [(d.key, c.ordinal) for d in documents for c in d.extracted.chunks]
        with transaction(conn):
            conn.execute("DELETE FROM seed_vector WHERE corpus_hash = ? AND model = ?", (corpus_hash, model))
            for (key, ordinal), vector in zip(keys, vectors, strict=True):
                array = np.asarray(vector, dtype=np.float32)
                conn.execute(
                    "INSERT INTO seed_vector (corpus_hash, document_key, ordinal, model, dim, vector) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (corpus_hash, key, ordinal, model, int(array.shape[0]), array.tobytes()),
                )
        log_event("seed_vectors_built", chunks=len(keys), model=model)
        rows = conn.execute(
            "SELECT document_key, ordinal, vector FROM seed_vector WHERE corpus_hash = ? AND model = ?",
            (corpus_hash, model),
        ).fetchall()
    return {
        (r["document_key"], int(r["ordinal"])): np.frombuffer(r["vector"], dtype=np.float32) for r in rows
    }


def workspace_of(services: Services, sid: str) -> OwnedNotebook | None:
    return next((n for n in services.repo.list_notebooks(sid) if n.kind == WORKSPACE_KIND), None)


def seed_workspace(services: Services, sid: str) -> OwnedNotebook:
    """Create the visitor's own copy of the curated workspace (no embedding calls once cached)."""
    vectors = seed_vectors(services)
    _, documents = corpus()
    notebook_id = services.repo.create_notebook(sid, WORKSPACE_TITLE, kind=WORKSPACE_KIND, limit=1)
    notebook = services.repo.get_notebook(sid, notebook_id)
    assert notebook is not None
    for document in documents:
        extracted = document.extracted
        services.repo.insert_source(
            NewSource(
                notebook=notebook,
                title=extracted.title,
                kind=extracted.kind,
                bytes=extracted.bytes,
                text=extracted.text,
                pages=None,
                page_starts=None,
                warnings=[],
                metadata=extracted.metadata,
                metadata_origin="curated",
                file_path=None,
                chunks=extracted.chunks,
                vectors=[vectors[(document.key, c.ordinal)] for c in extracted.chunks],
                vector_model=services.settings.model_embedding,
            )
        )
    log_event("workspace_seeded", session=sid, notebook=notebook_id, sources=len(documents))
    return notebook


def ensure_workspace(services: Services, sid: str) -> None:
    """Workspace hook: every visitor gets their own copy on the first visit."""
    if workspace_of(services, sid) is None:
        try:
            seed_workspace(services, sid)
        except CapacityReached:
            pass  # a parallel first visit seeded it
        except Exception as exc:
            log_event("workspace_seed_failed", session=sid, error_type=type(exc).__name__)


def reset_workspace(services: Services, sid: str) -> OwnedNotebook:
    existing = workspace_of(services, sid)
    if existing is not None:
        services.repo.delete_notebook(sid, existing.id)
    return seed_workspace(services, sid)
