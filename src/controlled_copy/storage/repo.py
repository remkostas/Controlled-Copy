"""Data access. Every read or write of visitor data is scoped to a session here.

Routes never query tables directly. Notebook and source lookups always join to
the owning session (`_owned_notebook`, `owned_source`), so a foreign ID behaves
exactly like a missing one: `None`, which the web layer turns into 404.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from controlled_copy.storage.db import transaction, utcnow

TOMBSTONE = "source_deleted"


class CapacityReached(Exception):
    """A per-notebook or per-visitor limit was reached (checked inside the write transaction)."""


def new_id() -> str:
    return secrets.token_urlsafe(12)


@dataclass(frozen=True)
class OwnedNotebook:
    """Proof that a notebook belongs to the current session.

    Only `Repo.get_notebook` and `Repo.list_notebooks` create it, after checking the
    session. Every notebook-level method takes it instead of a bare ID, so code that
    forgets the ownership check fails at once instead of leaking another visitor's data.
    """

    id: str
    session_id: str
    kind: str
    title: str
    suggestions_key: str | None = None
    suggestions_json: str | None = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def keys(self) -> list[str]:
        return ["id", "session_id", "kind", "title", "suggestions_key", "suggestions_json"]


def _owned(notebook: OwnedNotebook) -> str:
    if not isinstance(notebook, OwnedNotebook):
        raise TypeError("pass the OwnedNotebook from Repo.get_notebook, not a raw notebook ID")
    return notebook.id


def _notebook(row: sqlite3.Row) -> OwnedNotebook:
    return OwnedNotebook(
        row["id"],
        row["session_id"],
        row["kind"],
        row["title"],
        row["suggestions_key"],
        row["suggestions_json"],
    )


@dataclass(frozen=True)
class ChunkRecord:
    ordinal: int
    locator: str
    page: int | None
    char_start: int
    char_end: int
    text: str


@dataclass(frozen=True)
class NewSource:
    notebook: OwnedNotebook
    title: str
    kind: str
    bytes: int
    text: str
    pages: int | None
    page_starts: list[int] | None
    warnings: list[str]
    metadata: dict[str, Any] | None
    metadata_origin: str
    file_path: str | None
    chunks: Sequence[ChunkRecord]
    vectors: Sequence[Sequence[float]]
    vector_model: str


class Repo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # Sessions -----------------------------------------------------------------
    def create_session(self) -> str:
        sid = secrets.token_urlsafe(24)
        now = utcnow()
        self.conn.execute(
            "INSERT INTO visitor_session (id, created_at, last_seen_at) VALUES (?, ?, ?)",
            (sid, now, now),
        )
        return sid

    def session_last_seen(self, sid: str) -> str | None:
        row = self.conn.execute("SELECT last_seen_at FROM visitor_session WHERE id = ?", (sid,)).fetchone()
        return row["last_seen_at"] if row else None

    def touch_session(self, sid: str) -> None:
        self.conn.execute("UPDATE visitor_session SET last_seen_at = ? WHERE id = ?", (utcnow(), sid))

    # Notebooks ----------------------------------------------------------------
    def list_notebooks(self, sid: str) -> list[OwnedNotebook]:
        rows = self.conn.execute(
            "SELECT * FROM notebook WHERE session_id = ? ORDER BY kind DESC, created_at, rowid",
            (sid,),
        ).fetchall()
        return [_notebook(row) for row in rows]

    def count_notebooks(self, sid: str, kind: str = "personal") -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM notebook WHERE session_id = ? AND kind = ?", (sid, kind)
        ).fetchone()
        return int(row["n"])

    def get_notebook(self, sid: str, notebook_id: str) -> OwnedNotebook | None:
        row = self._owned_notebook(sid, notebook_id)
        return _notebook(row) if row is not None else None

    def _owned_notebook(self, sid: str, notebook_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM notebook WHERE id = ? AND session_id = ?", (notebook_id, sid)
        ).fetchone()

    def create_notebook(self, sid: str, title: str, kind: str = "personal", limit: int | None = None) -> str:
        notebook_id = new_id()
        with transaction(self.conn):
            if limit is not None and self.count_notebooks(sid, kind) >= limit:
                raise CapacityReached
            self.conn.execute(
                "INSERT INTO notebook (id, session_id, kind, title, created_at) VALUES (?, ?, ?, ?, ?)",
                (notebook_id, sid, kind, title, utcnow()),
            )
        return notebook_id

    def delete_notebook(self, sid: str, notebook_id: str) -> list[str] | None:
        """Delete a notebook and everything in it. Returns file paths to unlink."""
        with transaction(self.conn):
            if self._owned_notebook(sid, notebook_id) is None:
                return None
            files = [
                row["file_path"]
                for row in self.conn.execute(
                    "SELECT file_path FROM source WHERE notebook_id = ? AND file_path IS NOT NULL",
                    (notebook_id,),
                )
            ]
            self.conn.execute("DELETE FROM notebook WHERE id = ?", (notebook_id,))
        return files

    def set_suggestions(self, notebook: OwnedNotebook, key: str, questions: list[str]) -> None:
        self.conn.execute(
            "UPDATE notebook SET suggestions_key = ?, suggestions_json = ? WHERE id = ?",
            (key, json.dumps(questions), _owned(notebook)),
        )

    # Sources ------------------------------------------------------------------
    def list_sources(self, notebook: OwnedNotebook) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT s.id, s.notebook_id, s.title, s.kind, s.bytes, s.pages, s.warnings_json, "
            "s.metadata_json, s.metadata_origin, s.file_path, s.created_at, length(s.text) AS char_count, "
            "(SELECT COUNT(DISTINCT CASE WHEN instr(c.locator, ' (part ') > 0 "
            " THEN substr(c.locator, 1, instr(c.locator, ' (part ') - 1) ELSE c.locator END) "
            " FROM chunk c WHERE c.source_id = s.id) AS section_count "
            "FROM source s WHERE s.notebook_id = ? ORDER BY s.created_at, s.rowid",
            (_owned(notebook),),
        ).fetchall()

    def count_sources(self, notebook: OwnedNotebook) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM source WHERE notebook_id = ?", (_owned(notebook),)
        ).fetchone()
        return int(row["n"])

    def owned_source(self, sid: str, source_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT s.* FROM source s JOIN notebook n ON n.id = s.notebook_id "
            "WHERE s.id = ? AND n.session_id = ?",
            (source_id, sid),
        ).fetchone()

    def sources_by_ids(self, notebook: OwnedNotebook, source_ids: Iterable[str]) -> list[sqlite3.Row]:
        """The selected sources that belong to this notebook (foreign IDs are dropped)."""
        notebook_id = _owned(notebook)
        ids = list(dict.fromkeys(source_ids))
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        return self.conn.execute(
            f"SELECT * FROM source WHERE notebook_id = ? AND id IN ({marks}) "  # noqa: S608 - placeholders only
            "ORDER BY created_at, rowid",
            (notebook_id, *ids),
        ).fetchall()

    def source_rows(self, source_ids: Sequence[str]) -> dict[str, sqlite3.Row]:
        """Rows by ID. Callers pass IDs already checked against the session."""
        if not source_ids:
            return {}
        marks = ",".join("?" * len(source_ids))
        rows = self.conn.execute(
            f"SELECT * FROM source WHERE id IN ({marks})",  # noqa: S608 - placeholders only
            tuple(source_ids),
        ).fetchall()
        return {row["id"]: row for row in rows}

    def insert_source(self, new: NewSource, limit: int | None = None) -> str:
        if len(new.chunks) != len(new.vectors):
            raise ValueError("every chunk needs exactly one vector")
        source_id = new_id()
        with transaction(self.conn):
            if limit is not None and self.count_sources(new.notebook) >= limit:
                raise CapacityReached
            self.conn.execute(
                "INSERT INTO source (id, notebook_id, title, kind, bytes, pages, page_starts_json, "
                "warnings_json, metadata_json, metadata_origin, text, file_path, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    source_id,
                    _owned(new.notebook),
                    new.title,
                    new.kind,
                    new.bytes,
                    new.pages,
                    json.dumps(new.page_starts) if new.page_starts is not None else None,
                    json.dumps(new.warnings),
                    json.dumps(new.metadata) if new.metadata is not None else None,
                    new.metadata_origin,
                    new.text,
                    new.file_path,
                    utcnow(),
                ),
            )
            for chunk, vector in zip(new.chunks, new.vectors, strict=True):
                cursor = self.conn.execute(
                    "INSERT INTO chunk (source_id, ordinal, locator, page, char_start, char_end, text) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        source_id,
                        chunk.ordinal,
                        chunk.locator,
                        chunk.page,
                        chunk.char_start,
                        chunk.char_end,
                        chunk.text,
                    ),
                )
                array = np.asarray(vector, dtype=np.float32)
                self.conn.execute(
                    "INSERT INTO chunk_vector (chunk_id, model, dim, vector) VALUES (?, ?, ?, ?)",
                    (cursor.lastrowid, new.vector_model, int(array.shape[0]), array.tobytes()),
                )
        return source_id

    def delete_source(self, sid: str, source_id: str) -> list[str] | None:
        """Delete a source with its chunks, vectors, index rows and dependent outputs.

        Chat answers and Studio outputs generated with the source's passages in the
        prompt keep their row but lose their content (tombstone), so the transcript
        shows that something was removed without keeping text derived from it.
        Returns the file paths to unlink, or None if the source does not exist
        for this session.
        """
        with transaction(self.conn):
            row = self.owned_source(sid, source_id)
            if row is None:
                return None
            self._tombstone_citing(row["notebook_id"], source_id)
            self.conn.execute("DELETE FROM source WHERE id = ?", (source_id,))
            self.conn.execute(
                "UPDATE notebook SET suggestions_key = NULL, suggestions_json = NULL WHERE id = ?",
                (row["notebook_id"],),
            )
        return [row["file_path"]] if row["file_path"] else []

    def _tombstone_citing(self, notebook_id: str, source_id: str) -> None:
        for table in ("chat_message", "studio_output"):
            rows = self.conn.execute(
                f"SELECT id, citations_json FROM {table} WHERE notebook_id = ? AND status != ?",  # noqa: S608 - fixed table names
                (notebook_id, TOMBSTONE),
            ).fetchall()
            for row in rows:
                cited = {c.get("source_id") for c in json.loads(row["citations_json"] or "[]")}
                if source_id not in cited:
                    continue
                if table == "chat_message":
                    self.conn.execute(
                        "UPDATE chat_message SET content = '{}', search_query = NULL, citations_json = '[]', "
                        "status = ? WHERE id = ?",
                        (TOMBSTONE, row["id"]),
                    )
                else:
                    self.conn.execute(
                        "UPDATE studio_output SET output_json = '{}', input = NULL, citations_json = '[]', "
                        "status = ? WHERE id = ?",
                        (TOMBSTONE, row["id"]),
                    )

    # Chunks and vectors -------------------------------------------------------
    # Chunk-level helpers take source IDs that callers got from sources_by_ids or
    # owned_source, i.e. IDs already checked against the session.
    def chunks_for_sources(self, source_ids: Sequence[str]) -> list[sqlite3.Row]:
        if not source_ids:
            return []
        marks = ",".join("?" * len(source_ids))
        return self.conn.execute(
            f"SELECT * FROM chunk WHERE source_id IN ({marks}) ORDER BY source_id, ordinal",  # noqa: S608
            tuple(source_ids),
        ).fetchall()

    def chunks_by_ids(self, chunk_ids: Sequence[int]) -> dict[int, sqlite3.Row]:
        if not chunk_ids:
            return {}
        marks = ",".join("?" * len(chunk_ids))
        rows = self.conn.execute(
            f"SELECT c.*, s.title AS source_title, s.metadata_json, s.metadata_origin, s.kind AS source_kind "  # noqa: S608
            f"FROM chunk c JOIN source s ON s.id = c.source_id WHERE c.id IN ({marks})",
            tuple(chunk_ids),
        ).fetchall()
        return {int(row["id"]): row for row in rows}

    def vectors_for_sources(self, source_ids: Sequence[str], model: str) -> tuple[list[int], np.ndarray]:
        """Vectors of the selected sources made by `model` (vectors of other models are not comparable)."""
        if not source_ids:
            return [], np.zeros((0, 0), dtype=np.float32)
        marks = ",".join("?" * len(source_ids))
        rows = self.conn.execute(
            f"SELECT v.chunk_id, v.vector FROM chunk_vector v JOIN chunk c ON c.id = v.chunk_id "  # noqa: S608
            f"WHERE c.source_id IN ({marks}) AND v.model = ? ORDER BY v.chunk_id",
            (*source_ids, model),
        ).fetchall()
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32)
        ids = [int(row["chunk_id"]) for row in rows]
        matrix = np.vstack([np.frombuffer(row["vector"], dtype=np.float32) for row in rows])
        return ids, matrix

    def fts_search(self, source_ids: Sequence[str], match: str, limit: int) -> list[int]:
        if not source_ids or not match:
            return []
        marks = ",".join("?" * len(source_ids))
        rows = self.conn.execute(
            "SELECT c.id FROM chunk_fts JOIN chunk c ON c.id = chunk_fts.rowid "  # noqa: S608 - placeholders only
            f"WHERE chunk_fts MATCH ? AND c.source_id IN ({marks}) "
            "ORDER BY bm25(chunk_fts) LIMIT ?",
            (match, *source_ids, limit),
        ).fetchall()
        return [int(row["id"]) for row in rows]

    # Chat ---------------------------------------------------------------------
    def add_turn(
        self,
        notebook: OwnedNotebook,
        question: str,
        answer: dict[str, Any],
        search_query: str | None,
        citations: list[dict[str, Any]],
        status: str,
    ) -> str:
        notebook_id = _owned(notebook)
        turn_id = new_id()
        now = utcnow()
        with transaction(self.conn):
            self.conn.execute(
                "INSERT INTO chat_message (id, notebook_id, turn_id, role, content, created_at) "
                "VALUES (?, ?, ?, 'user', ?, ?)",
                (new_id(), notebook_id, turn_id, question, now),
            )
            self.conn.execute(
                "INSERT INTO chat_message (id, notebook_id, turn_id, role, content, search_query, "
                "citations_json, status, created_at) VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?)",
                (
                    new_id(),
                    notebook_id,
                    turn_id,
                    json.dumps(answer),
                    search_query,
                    json.dumps(citations),
                    status,
                    now,
                ),
            )
        return turn_id

    def list_messages(self, notebook: OwnedNotebook) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM chat_message WHERE notebook_id = ? ORDER BY created_at, rowid",
            (_owned(notebook),),
        ).fetchall()

    # Studio -------------------------------------------------------------------
    def add_output(
        self,
        notebook: OwnedNotebook,
        template: str,
        input_text: str | None,
        output: dict[str, Any],
        citations: list[dict[str, Any]],
        status: str,
    ) -> str:
        output_id = new_id()
        self.conn.execute(
            "INSERT INTO studio_output (id, notebook_id, template, input, output_json, citations_json, "
            "status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                output_id,
                _owned(notebook),
                template,
                input_text,
                json.dumps(output),
                json.dumps(citations),
                status,
                utcnow(),
            ),
        )
        return output_id

    def list_outputs(self, notebook: OwnedNotebook) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM studio_output WHERE notebook_id = ? ORDER BY created_at DESC, rowid DESC",
            (_owned(notebook),),
        ).fetchall()

    def get_output(self, notebook: OwnedNotebook, output_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM studio_output WHERE id = ? AND notebook_id = ?", (output_id, _owned(notebook))
        ).fetchone()

    # Model-call accounting ------------------------------------------------------
    def record_model_call(self, sid: str | None, kind: str) -> None:
        self.conn.execute(
            "INSERT INTO model_call (session_id, kind, at) VALUES (?, ?, ?)", (sid, kind, utcnow())
        )

    def count_model_calls(self, since: str, sid: str | None = None) -> int:
        if sid is None:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM model_call WHERE at >= ?", (since,)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) AS n FROM model_call WHERE session_id = ? AND at >= ?", (sid, since)
            ).fetchone()
        return int(row["n"])

    # Retention ------------------------------------------------------------------
    def purge_expired(self, retention_hours: int, now: datetime | None = None) -> tuple[int, list[str]]:
        """Delete sessions not seen within the retention window, with all their data."""
        now = now or datetime.now(UTC)
        cutoff = (now - timedelta(hours=retention_hours)).isoformat(timespec="seconds")
        with transaction(self.conn):
            expired = [
                row["id"]
                for row in self.conn.execute(
                    "SELECT id FROM visitor_session WHERE last_seen_at < ?", (cutoff,)
                )
            ]
            files: list[str] = []
            for sid in expired:
                files.extend(
                    row["file_path"]
                    for row in self.conn.execute(
                        "SELECT s.file_path FROM source s JOIN notebook n ON n.id = s.notebook_id "
                        "WHERE n.session_id = ? AND s.file_path IS NOT NULL",
                        (sid,),
                    )
                )
                self.conn.execute("DELETE FROM visitor_session WHERE id = ?", (sid,))
            old_calls = (now - timedelta(days=2)).isoformat(timespec="seconds")
            self.conn.execute("DELETE FROM model_call WHERE at < ?", (old_calls,))
        return len(expired), files

    def referenced_files(self) -> set[str]:
        return {
            Path(row["file_path"]).name
            for row in self.conn.execute("SELECT file_path FROM source WHERE file_path IS NOT NULL")
        }
