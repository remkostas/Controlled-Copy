"""Data access. Every read or write of visitor data is scoped to a session here.

Routes never query tables directly. Notebook and source lookups always join to
the owning session (`_owned_notebook`, `owned_source`), so a foreign ID behaves
exactly like a missing one: `None`, which the web layer turns into 404.
"""

from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
import time
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

from controlled_copy.errors import UserFacingError
from controlled_copy.logs import log_event
from controlled_copy.storage.db import transaction, utcnow

TOMBSTONE = "source_deleted"


class CapacityReached(UserFacingError):
    """A per-notebook or per-visitor limit was reached (checked inside the write transaction)."""


def notebooks_full(limit: int) -> CapacityReached:
    return CapacityReached(f"You can have at most {limit} notebooks. Delete one to create another.", 409)


def sources_full(limit: int) -> CapacityReached:
    return CapacityReached(f"A notebook holds at most {limit} sources.", 409)


def notebook_gone() -> UserFacingError:
    return UserFacingError("This notebook was deleted.", 404)


class Stored(NamedTuple):
    """What a write actually stored: its ID and status (TOMBSTONE when a source it depends
    on was deleted while it was being generated)."""

    id: str
    status: str


def visitor_storage_full(limit_mb: int) -> CapacityReached:
    return CapacityReached(
        f"You have added the most this demo stores per visitor ({limit_mb:,} MB). "
        "Delete a source or notebook to add another.",
        409,
    )


def storage_full() -> CapacityReached:
    return CapacityReached(
        "The demo's storage is full right now. Viewing still works; please try again later.", 507
    )


def estimated_growth(text: str, chunk_texts: list[str], vector_bytes: int) -> int:
    """What storing a source adds to the database, generously: the text once in the source row,
    again in its chunks and once more in the full-text index, the vectors, and row overhead."""
    text_bytes = max(len(text.encode()), sum(len(c.encode()) for c in chunk_texts))
    return 3 * text_bytes + vector_bytes + 256 * len(chunk_texts)


def check_free_disk(directory: Path, needed_bytes: int, min_free_bytes: int) -> None:
    """Raise storage_full if writing `needed_bytes` would leave less than the floor free."""
    if shutil.disk_usage(directory).free - needed_bytes < min_free_bytes:
        raise storage_full()


def characters_full(limit: int) -> CapacityReached:
    return CapacityReached(
        f"A notebook holds at most {limit:,} characters of text. Delete a source to add this one.", 409
    )


def new_id() -> str:
    return secrets.token_urlsafe(12)


def _marks(values: Sequence[Any]) -> str:
    """'?,?,?' for an IN clause; only placeholders ever go into the SQL text (callers ensure non-empty)."""
    return ",".join("?" * len(values))


# Source columns without the full text, which can be several megabytes.
SOURCE_COLUMNS = (
    "s.id, s.notebook_id, s.title, s.kind, s.bytes, s.pages, s.page_starts_json, s.warnings_json, "
    "s.metadata_json, s.metadata_origin, s.file_path, s.created_at"
)
CHUNK_COLUMNS = "c.*, s.title AS source_title, s.metadata_json, s.metadata_origin, s.kind AS source_kind"


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


def _owned(notebook: OwnedNotebook) -> str:
    if not isinstance(notebook, OwnedNotebook):
        raise TypeError("pass the OwnedNotebook from Repo.get_notebook, not a raw notebook ID")
    return notebook.id


def _notebook(row: sqlite3.Row) -> OwnedNotebook:
    return OwnedNotebook(**{f.name: row[f.name] for f in fields(OwnedNotebook)})


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
    def __init__(self, conn: sqlite3.Connection, visible_kinds: tuple[str, ...] | None = None) -> None:
        """`visible_kinds` limits what a visitor can open: personal notebooks plus the kinds of
        loaded layers. None (maintenance, tests) sees every kind."""
        self.conn = conn
        self.visible_kinds = visible_kinds

    def _kinds(self, column: str) -> tuple[str, tuple[str, ...]]:
        if self.visible_kinds is None:
            return "", ()
        marks = ", ".join("?" for _ in self.visible_kinds)
        return f" AND {column} IN ({marks})", self.visible_kinds

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
        """Layer notebooks first, then personal ones in creation order."""
        clause, kinds = self._kinds("kind")
        rows = self.conn.execute(
            f"SELECT * FROM notebook WHERE session_id = ?{clause} "  # noqa: S608 - placeholders only
            "ORDER BY kind = 'personal', created_at, rowid",
            (sid, *kinds),
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
        clause, kinds = self._kinds("kind")
        return self.conn.execute(
            f"SELECT * FROM notebook WHERE id = ? AND session_id = ?{clause}",  # noqa: S608 - placeholders only
            (notebook_id, sid, *kinds),
        ).fetchone()

    def create_notebook(self, sid: str, title: str, kind: str = "personal", limit: int | None = None) -> str:
        notebook_id = new_id()
        with transaction(self.conn):
            if limit is not None and self.count_notebooks(sid, kind) >= limit:
                raise notebooks_full(limit)
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

    def set_suggestions(
        self, notebook: OwnedNotebook, key: str, questions: list[str], source_ids: Sequence[str]
    ) -> bool:
        """Store suggestions unless the notebook's sources changed while they were generated."""
        notebook_id = _owned(notebook)
        with transaction(self.conn):
            current = sorted(
                row["id"]
                for row in self.conn.execute("SELECT id FROM source WHERE notebook_id = ?", (notebook_id,))
            )
            if current != sorted(source_ids):
                return False
            self.conn.execute(
                "UPDATE notebook SET suggestions_key = ?, suggestions_json = ? WHERE id = ?",
                (key, json.dumps(questions), notebook_id),
            )
        return True

    # Sources ------------------------------------------------------------------
    def list_sources(self, notebook: OwnedNotebook) -> list[sqlite3.Row]:
        return self.conn.execute(
            f"SELECT {SOURCE_COLUMNS}, "  # noqa: S608 - fixed column list
            "CASE WHEN s.kind IN ('txt', 'paste') THEN length(s.text) END AS char_count, "
            "CASE WHEN s.kind = 'md' THEN (SELECT COUNT(DISTINCT CASE WHEN instr(c.locator, ' (part ') > 0 "
            " THEN substr(c.locator, 1, instr(c.locator, ' (part ') - 1) ELSE c.locator END) "
            " FROM chunk c WHERE c.source_id = s.id) END AS section_count "
            "FROM source s WHERE s.notebook_id = ? ORDER BY s.created_at, s.rowid",
            (_owned(notebook),),
        ).fetchall()

    def count_sources(self, notebook: OwnedNotebook) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM source WHERE notebook_id = ?", (_owned(notebook),)
        ).fetchone()
        return int(row["n"])

    def session_bytes(self, sid: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(s.bytes), 0) AS n FROM source s JOIN notebook n ON n.id = s.notebook_id "
            "WHERE n.session_id = ?",
            (sid,),
        ).fetchone()
        return int(row["n"])

    def total_bytes(self) -> int:
        return int(self.conn.execute("SELECT COALESCE(SUM(bytes), 0) AS n FROM source").fetchone()["n"])

    def check_storage(self, sid: str, new_bytes: int, visitor_limit_mb: int, total_limit_mb: int) -> None:
        """Raise CapacityReached if `new_bytes` more would exceed the visitor's or the demo's limit."""
        if self.session_bytes(sid) + new_bytes > visitor_limit_mb * 1024 * 1024:
            raise visitor_storage_full(visitor_limit_mb)
        if self.total_bytes() + new_bytes > total_limit_mb * 1024 * 1024:
            raise storage_full()

    def count_chars(self, notebook: OwnedNotebook) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(length(text)), 0) AS n FROM source WHERE notebook_id = ?",
            (_owned(notebook),),
        ).fetchone()
        return int(row["n"])

    def owned_source(self, sid: str, source_id: str, with_text: bool = False) -> sqlite3.Row | None:
        columns = f"{SOURCE_COLUMNS}, s.text" if with_text else SOURCE_COLUMNS
        clause, kinds = self._kinds("n.kind")
        return self.conn.execute(
            f"SELECT {columns} FROM source s JOIN notebook n ON n.id = s.notebook_id "  # noqa: S608 - fixed columns
            f"WHERE s.id = ? AND n.session_id = ?{clause}",
            (source_id, sid, *kinds),
        ).fetchone()

    def sources_by_ids(
        self, notebook: OwnedNotebook, source_ids: Iterable[str], with_text: bool = False
    ) -> list[sqlite3.Row]:
        """The selected sources that belong to this notebook (foreign IDs are dropped)."""
        notebook_id = _owned(notebook)
        ids = list(dict.fromkeys(source_ids))
        if not ids:
            return []
        columns = f"{SOURCE_COLUMNS}, s.text" if with_text else SOURCE_COLUMNS
        return self.conn.execute(
            f"SELECT {columns} FROM source s WHERE s.notebook_id = ? AND s.id IN ({_marks(ids)}) "  # noqa: S608
            "ORDER BY s.created_at, s.rowid",
            (notebook_id, *ids),
        ).fetchall()

    def insert_source(
        self,
        new: NewSource,
        limit: int | None = None,
        char_limit: int | None = None,
        storage_limits_mb: tuple[int, int] | None = None,
        disk_floor: tuple[Path, int] | None = None,
    ) -> str:
        """`disk_floor` (data directory, bytes to keep free) is checked inside the write
        transaction, against what this insert adds to the database. Writers take turns here,
        so two uploads cannot both pass the floor on the same free space (full audit
        re-check RCK-04); an uploaded file written before this call is already on disk."""
        if len(new.chunks) != len(new.vectors):
            raise ValueError("every chunk needs exactly one vector")
        source_id = new_id()
        with transaction(self.conn):
            # The visitor logged out or deleted the notebook while this upload was indexed.
            self._require_notebook(_owned(new.notebook))
            if limit is not None and self.count_sources(new.notebook) >= limit:
                raise sources_full(limit)
            if char_limit is not None and self.count_chars(new.notebook) + len(new.text) > char_limit:
                raise characters_full(char_limit)
            if storage_limits_mb is not None:
                self.check_storage(new.notebook.session_id, new.bytes, *storage_limits_mb)
            if disk_floor is not None:
                vector_bytes = sum(4 * len(v) for v in new.vectors)
                growth = estimated_growth(new.text, [c.text for c in new.chunks], vector_bytes)
                check_free_disk(disk_floor[0], growth, disk_floor[1])
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

        Chat turns and Studio outputs whose lineage includes the source keep their row
        but lose their content (tombstone), so the transcript shows that something was
        removed without keeping text derived from it. Returns the file paths to unlink,
        or None if the source does not exist for this session.
        """
        with transaction(self.conn):
            row = self.owned_source(sid, source_id)
            if row is None:
                return None
            self._tombstone_dependents(row["notebook_id"], source_id)
            self.conn.execute("DELETE FROM source WHERE id = ?", (source_id,))
            self.conn.execute(
                "UPDATE notebook SET suggestions_key = NULL, suggestions_json = NULL WHERE id = ?",
                (row["notebook_id"],),
            )
        return [row["file_path"]] if row["file_path"] else []

    def _tombstone_dependents(self, notebook_id: str, source_id: str) -> None:
        depends = "EXISTS (SELECT 1 FROM json_each(lineage_json) WHERE value = ?)"
        # Whole turns: the answer, its search query, and the question (which may be a
        # suggested question generated from source text).
        self.conn.execute(
            "UPDATE chat_message SET content = CASE role WHEN 'user' THEN '' ELSE '{}' END, "  # noqa: S608 - fixed SQL
            "search_query = NULL, lineage_json = '[]', status = ? "
            "WHERE notebook_id = ? AND turn_id IN (SELECT turn_id FROM chat_message "
            f"WHERE notebook_id = ? AND role = 'assistant' AND {depends})",
            (TOMBSTONE, notebook_id, notebook_id, source_id),
        )
        self.conn.execute(
            "UPDATE studio_output SET output_json = '{}', input = NULL, lineage_json = '[]', status = ? "  # noqa: S608
            f"WHERE notebook_id = ? AND {depends}",
            (TOMBSTONE, notebook_id, source_id),
        )

    def _all_sources_exist(self, notebook_id: str, lineage: Collection[str]) -> bool:
        wanted = set(lineage)
        if not wanted:
            return True
        row = self.conn.execute(
            f"SELECT COUNT(*) AS n FROM source WHERE notebook_id = ? AND id IN ({_marks(wanted)})",  # noqa: S608
            (notebook_id, *wanted),
        ).fetchone()
        return int(row["n"]) == len(wanted)

    def checkpoint(self, attempts: int = 5) -> bool:
        """Fold the write-ahead log into the database so deleted pages do not linger in it.

        A reader holding an older snapshot blocks a complete checkpoint; it is retried briefly,
        and an incomplete one is reported (the hourly purge retries). Returns True when the log
        was fully folded and truncated."""
        # A checkpoint waits on readers through the busy handler; keep that wait short here so
        # a deletion never hangs on another visitor's read (the connection default is 15 s).
        previous = self.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.conn.execute("PRAGMA busy_timeout = 100")
        try:
            for attempt in range(attempts):
                busy = self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]
                if not busy:
                    return True
                time.sleep(0.05 * (attempt + 1))
        finally:
            self.conn.execute(f"PRAGMA busy_timeout = {int(previous)}")
        log_event("checkpoint_incomplete")
        return False

    # Chunks and vectors -------------------------------------------------------
    # Chunk-level helpers take source IDs that callers got from sources_by_ids or
    # owned_source, i.e. IDs already checked against the session.
    def chunks_for_sources(self, source_ids: Sequence[str]) -> list[sqlite3.Row]:
        if not source_ids:
            return []
        return self.conn.execute(
            f"SELECT {CHUNK_COLUMNS} FROM chunk c JOIN source s ON s.id = c.source_id "  # noqa: S608
            f"WHERE c.source_id IN ({_marks(source_ids)}) ORDER BY c.source_id, c.ordinal",
            tuple(source_ids),
        ).fetchall()

    def chunks_by_ids(self, chunk_ids: Sequence[int]) -> dict[int, sqlite3.Row]:
        if not chunk_ids:
            return {}
        rows = self.conn.execute(
            f"SELECT {CHUNK_COLUMNS} FROM chunk c JOIN source s ON s.id = c.source_id "  # noqa: S608
            f"WHERE c.id IN ({_marks(chunk_ids)})",
            tuple(chunk_ids),
        ).fetchall()
        return {int(row["id"]): row for row in rows}

    def locator_at(self, source_id: str, offset: int) -> str | None:
        """The section or page of the chunk containing a character offset."""
        row = self.conn.execute(
            "SELECT locator FROM chunk WHERE source_id = ? AND char_start <= ? AND char_end > ? "
            "ORDER BY ordinal LIMIT 1",
            (source_id, offset, offset),
        ).fetchone()
        return row["locator"] if row else None

    def vectors_for_sources(self, source_ids: Sequence[str], model: str) -> tuple[list[int], np.ndarray]:
        """Vectors of the selected sources made by `model` (vectors of other models are not comparable)."""
        if not source_ids:
            return [], np.zeros((0, 0), dtype=np.float32)
        rows = self.conn.execute(
            f"SELECT v.chunk_id, v.vector FROM chunk_vector v JOIN chunk c ON c.id = v.chunk_id "  # noqa: S608
            f"WHERE c.source_id IN ({_marks(source_ids)}) AND v.model = ? ORDER BY v.chunk_id",
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
        rows = self.conn.execute(
            "SELECT c.id FROM chunk_fts JOIN chunk c ON c.id = chunk_fts.rowid "  # noqa: S608 - placeholders only
            f"WHERE chunk_fts MATCH ? AND c.source_id IN ({_marks(source_ids)}) "
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
        lineage: Collection[str],
        status: str,
        chat_epoch: int | None = None,
    ) -> Stored:
        """Store a turn. `lineage` names every source the turn's text depends on. Returns what
        was stored: callers answer with that, never with text the store discarded.
        `chat_epoch` is the notebook's chat generation when the question arrived: if New chat
        ran since, nothing is stored and the turn comes back as a tombstone."""
        notebook_id = _owned(notebook)
        turn_id = new_id()
        now = utcnow()
        with transaction(self.conn):
            self._require_notebook(notebook_id)
            if chat_epoch is not None and self._chat_epoch(notebook_id) != chat_epoch:
                return Stored(turn_id, TOMBSTONE)
            if not self._all_sources_exist(notebook_id, lineage):
                # A source was deleted while the model was answering: keep no derived text.
                question, answer, search_query, lineage, status = "", {}, None, [], TOMBSTONE
            self.conn.execute(
                "INSERT INTO chat_message (id, notebook_id, turn_id, role, content, status, created_at) "
                "VALUES (?, ?, ?, 'user', ?, ?, ?)",
                (new_id(), notebook_id, turn_id, question, status, now),
            )
            self.conn.execute(
                "INSERT INTO chat_message (id, notebook_id, turn_id, role, content, search_query, "
                "lineage_json, status, created_at) VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?)",
                (
                    new_id(),
                    notebook_id,
                    turn_id,
                    json.dumps(answer),
                    search_query,
                    json.dumps(sorted(lineage)),
                    status,
                    now,
                ),
            )
        return Stored(turn_id, status)

    def _require_notebook(self, notebook_id: str) -> None:
        """Inside a write: the notebook was not deleted while its content was generated."""
        if self.conn.execute("SELECT 1 FROM notebook WHERE id = ?", (notebook_id,)).fetchone() is None:
            raise notebook_gone()

    def clear_chat(self, notebook: OwnedNotebook) -> int:
        """Start a new chat: delete every turn of the notebook and raise its chat generation,
        so an answer still being generated is not stored. Sources and Studio outputs stay."""
        notebook_id = _owned(notebook)
        with transaction(self.conn):
            self.conn.execute("UPDATE notebook SET chat_epoch = chat_epoch + 1 WHERE id = ?", (notebook_id,))
            return self.conn.execute(
                "DELETE FROM chat_message WHERE notebook_id = ?", (notebook_id,)
            ).rowcount

    def chat_epoch(self, notebook: OwnedNotebook) -> int:
        """The notebook's chat generation; New chat raises it."""
        return self._chat_epoch(_owned(notebook))

    def _chat_epoch(self, notebook_id: str) -> int:
        row = self.conn.execute("SELECT chat_epoch FROM notebook WHERE id = ?", (notebook_id,)).fetchone()
        return int(row[0]) if row else 0

    def list_turns(self, notebook: OwnedNotebook) -> list[sqlite3.Row]:
        """One row per turn: question, answer JSON, search query, lineage and status."""
        return self.conn.execute(
            "SELECT a.turn_id, u.content AS question, a.content AS answer_json, a.search_query, "
            "a.lineage_json, a.status FROM chat_message a "
            "JOIN chat_message u ON u.turn_id = a.turn_id AND u.role = 'user' "
            "WHERE a.notebook_id = ? AND a.role = 'assistant' ORDER BY a.created_at, a.rowid",
            (_owned(notebook),),
        ).fetchall()

    # Studio -------------------------------------------------------------------
    def add_output(
        self,
        notebook: OwnedNotebook,
        template: str,
        input_text: str | None,
        output: dict[str, Any],
        lineage: Collection[str],
        status: str,
    ) -> Stored:
        """Store a Studio output. `lineage` names every source its text depends on. Returns
        what was stored (see add_turn)."""
        output_id = new_id()
        notebook_id = _owned(notebook)
        with transaction(self.conn):
            self._require_notebook(notebook_id)
            if not self._all_sources_exist(notebook_id, lineage):
                input_text, output, lineage, status = None, {}, [], TOMBSTONE
            self.conn.execute(
                "INSERT INTO studio_output (id, notebook_id, template, input, output_json, lineage_json, "
                "status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    output_id,
                    notebook_id,
                    template,
                    input_text,
                    json.dumps(output),
                    json.dumps(sorted(lineage)),
                    status,
                    utcnow(),
                ),
            )
        return Stored(output_id, status)

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
    def record_model_call(self, sid: str | None, kind: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO model_call (session_id, kind, at) VALUES (?, ?, ?)", (sid, kind, utcnow())
        )
        return int(cursor.lastrowid or 0)

    def add_model_cost(self, call_id: int, cost_usd: float) -> None:
        self.conn.execute("UPDATE model_call SET cost_usd = ? WHERE id = ?", (cost_usd, call_id))

    def spent_usd(self, since: str) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS usd FROM model_call WHERE at >= ?", (since,)
        ).fetchone()
        return float(row["usd"])

    def count_model_calls(self, since: str, sid: str | None = None) -> int:
        if sid is None:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM model_call WHERE at >= ?", (since,)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) AS n FROM model_call WHERE session_id = ? AND at >= ?", (sid, since)
            ).fetchone()
        return int(row["n"])

    # Retention ------------------------------------------------------------------
    def delete_session(self, sid: str) -> list[str]:
        """Log out: delete the session with all its data now, as the purge would after the
        retention window. Returns the uploaded files to remove."""
        with transaction(self.conn):
            files = [
                row["file_path"]
                for row in self.conn.execute(
                    "SELECT s.file_path FROM source s JOIN notebook n ON n.id = s.notebook_id "
                    "WHERE n.session_id = ? AND s.file_path IS NOT NULL",
                    (sid,),
                )
            ]
            self.conn.execute("DELETE FROM visitor_session WHERE id = ?", (sid,))
        return files

    def purge_expired(self, retention_hours: int, now: datetime | None = None) -> tuple[int, list[str]]:
        """Delete sessions not seen within the retention window, with all their data."""
        now = now or datetime.now(UTC)
        cutoff = (now - timedelta(hours=retention_hours)).isoformat(timespec="seconds")
        with transaction(self.conn):
            files = [
                row["file_path"]
                for row in self.conn.execute(
                    "SELECT s.file_path FROM source s JOIN notebook n ON n.id = s.notebook_id "
                    "JOIN visitor_session v ON v.id = n.session_id "
                    "WHERE v.last_seen_at < ? AND s.file_path IS NOT NULL",
                    (cutoff,),
                )
            ]
            expired = self.conn.execute(
                "DELETE FROM visitor_session WHERE last_seen_at < ?", (cutoff,)
            ).rowcount
            old_calls = (now - timedelta(days=2)).isoformat(timespec="seconds")
            self.conn.execute("DELETE FROM model_call WHERE at < ?", (old_calls,))
        return expired, files

    def referenced_files(self) -> set[str]:
        return {
            Path(row["file_path"]).name
            for row in self.conn.execute("SELECT file_path FROM source WHERE file_path IS NOT NULL")
        }
