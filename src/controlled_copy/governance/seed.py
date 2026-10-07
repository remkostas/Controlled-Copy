"""The per-visitor "Inbound Operations" workspace, seeded from the curated corpus.

The corpus is embedded once per corpus version and embedding model; the vectors are
kept in `seed_vector`. Seeding a visitor's copy, and every Reset, copies chunks and
vectors from there, so neither makes an embedding call (TC-GOV-002).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np

from controlled_copy.ingestion import pipeline
from controlled_copy.logs import log_event
from controlled_copy.services import Services
from controlled_copy.storage.db import transaction
from controlled_copy.storage.repo import CapacityReached, NewSource, OwnedNotebook

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
    """The curated documents (parsed once) and a hash that changes when any file, or the
    text that is embedded for it (title and chunking), changes."""
    folder = demo_data_dir() / "inbound-operations"
    digest = hashlib.sha256()
    documents = []
    for path in sorted(folder.glob("*.md")):
        data = path.read_bytes()
        digest.update(path.name.encode() + b"\0" + data)
        extracted = pipeline.extract_upload(
            path.name, data, max_pages=150, timeout=30, memory_mb=512, title_limit=200
        )
        extracted.metadata_origin = "curated"  # front matter parsed by extract_upload
        for chunk in extracted.chunks:
            digest.update(b"\0" + pipeline.embedding_input(extracted.title, chunk).encode())
        documents.append(SeedDocument(path.name, extracted))
    return digest.hexdigest()[:16], tuple(documents)


@cache
def demo_config() -> dict[str, Any]:
    """The curated workspace's settings from demo-data/scenarios.json: its title, the default
    site and role of the context bar and the example situations. The domain lives there,
    not in code (product-concepts.md section 9, guardrail 3)."""
    path = demo_data_dir() / "scenarios.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def scenarios() -> list[dict[str, Any]]:
    return list(demo_config().get("scenarios", []))


def workspace_title() -> str:
    return str(demo_config().get("workspace_title") or "Demo workspace")


def default_role() -> str | None:
    role = demo_config().get("default_context", {}).get("role")
    return str(role) if role else None


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
    """Create the visitor's own copy of the curated workspace (no embedding calls once cached).
    One transaction: a failure or crash halfway never leaves a partial copy behind."""
    vectors = seed_vectors(services)
    with transaction(services.repo.conn):
        notebook = _copy_corpus(services, sid, vectors)
    log_event("workspace_seeded", session=sid, notebook=notebook.id, sources=len(corpus()[1]))
    return notebook


def _copy_corpus(services: Services, sid: str, vectors: dict[tuple[str, int], np.ndarray]) -> OwnedNotebook:
    _, documents = corpus()
    notebook_id = services.repo.create_notebook(sid, workspace_title(), kind=WORKSPACE_KIND, limit=1)
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
    return notebook


class WorkspaceSeeder:
    """Workspace hook: every visitor gets their own copy on the first visit. After a failure
    (for example a cold vector cache while the provider is down) page loads skip seeding for
    a minute instead of each waiting on, and paying for, another embedding attempt.
    One instance per app, so the cooldown never leaks between apps."""

    retry_seconds = 60.0

    def __init__(self) -> None:
        self.failed_at: float | None = None

    def __call__(self, services: Services, sid: str) -> None:
        if workspace_of(services, sid) is not None:
            return
        if self.failed_at is not None and time.monotonic() - self.failed_at < self.retry_seconds:
            return
        try:
            seed_workspace(services, sid)
        except CapacityReached:
            pass  # a parallel first visit seeded it
        except Exception as exc:
            self.failed_at = time.monotonic()
            log_event("workspace_seed_failed", session=sid, error_type=type(exc).__name__)
        else:
            self.failed_at = None


def reset_workspace(services: Services, sid: str) -> tuple[OwnedNotebook, list[str]]:
    """A fresh copy of the workspace, and the uploaded files the old copy leaves behind.
    The vectors are loaded first and the swap is one transaction, so a failure (a cold
    cache with the provider down, a crash) leaves the old copy and its files in place."""
    vectors = seed_vectors(services)
    with transaction(services.repo.conn):
        existing = workspace_of(services, sid)
        files = (services.repo.delete_notebook(sid, existing.id) or []) if existing is not None else []
        notebook = _copy_corpus(services, sid, vectors)
    log_event("workspace_seeded", session=sid, notebook=notebook.id, sources=len(corpus()[1]))
    return notebook, files
