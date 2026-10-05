"""SQLite connection handling and migrations.

One connection per request. Foreign keys are on, so deleting a parent row
removes its children; `secure_delete` overwrites deleted content in the file.
Migrations are applied in order and recorded; stage 2 and 3 migrations may only
add tables or nullable columns (D-032).
"""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class Migration:
    id: str
    sql: str


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=15, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA secure_delete = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """A write transaction; nested use becomes a savepoint instead of an error."""
    if conn.in_transaction:
        name = f"sp_{secrets.token_hex(4)}"
        conn.execute(f"SAVEPOINT {name}")
        try:
            yield conn
        except BaseException:
            conn.execute(f"ROLLBACK TO {name}")
            conn.execute(f"RELEASE {name}")
            raise
        else:
            conn.execute(f"RELEASE {name}")
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


CORE_MIGRATIONS: list[Migration] = [
    Migration(
        "0001_core",
        """
        CREATE TABLE visitor_session (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        CREATE INDEX visitor_session_last_seen ON visitor_session(last_seen_at);

        CREATE TABLE notebook (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES visitor_session(id) ON DELETE CASCADE,
            kind TEXT NOT NULL CHECK (kind IN ('personal', 'ops_workspace')),
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            suggestions_key TEXT,
            suggestions_json TEXT
        );
        CREATE INDEX notebook_session ON notebook(session_id);

        CREATE TABLE source (
            id TEXT PRIMARY KEY,
            notebook_id TEXT NOT NULL REFERENCES notebook(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            kind TEXT NOT NULL CHECK (kind IN ('pdf', 'txt', 'md', 'paste')),
            bytes INTEGER NOT NULL,
            pages INTEGER,
            page_starts_json TEXT,
            warnings_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT,
            metadata_origin TEXT NOT NULL DEFAULT 'none'
                CHECK (metadata_origin IN ('curated', 'asserted', 'none')),
            text TEXT NOT NULL,
            file_path TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX source_notebook ON source(notebook_id);

        CREATE TABLE chunk (
            id INTEGER PRIMARY KEY,
            source_id TEXT NOT NULL REFERENCES source(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            locator TEXT NOT NULL,
            page INTEGER,
            char_start INTEGER NOT NULL,
            char_end INTEGER NOT NULL,
            text TEXT NOT NULL
        );
        CREATE INDEX chunk_source ON chunk(source_id);

        CREATE TABLE chunk_vector (
            chunk_id INTEGER PRIMARY KEY REFERENCES chunk(id) ON DELETE CASCADE,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL
        );

        CREATE VIRTUAL TABLE chunk_fts USING fts5(body, tokenize = 'porter unicode61');
        CREATE TRIGGER chunk_fts_insert AFTER INSERT ON chunk BEGIN
            INSERT INTO chunk_fts(rowid, body) VALUES (new.id, new.locator || char(10) || new.text);
        END;
        CREATE TRIGGER chunk_fts_delete AFTER DELETE ON chunk BEGIN
            DELETE FROM chunk_fts WHERE rowid = old.id;
        END;

        CREATE TABLE chat_message (
            id TEXT PRIMARY KEY,
            notebook_id TEXT NOT NULL REFERENCES notebook(id) ON DELETE CASCADE,
            turn_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            search_query TEXT,
            lineage_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'ok',
            created_at TEXT NOT NULL
        );
        CREATE INDEX chat_message_notebook ON chat_message(notebook_id, created_at);

        CREATE TABLE studio_output (
            id TEXT PRIMARY KEY,
            notebook_id TEXT NOT NULL REFERENCES notebook(id) ON DELETE CASCADE,
            template TEXT NOT NULL,
            input TEXT,
            output_json TEXT NOT NULL,
            lineage_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'ok',
            created_at TEXT NOT NULL
        );
        CREATE INDEX studio_output_notebook ON studio_output(notebook_id, created_at);

        CREATE TABLE model_call (
            id INTEGER PRIMARY KEY,
            session_id TEXT REFERENCES visitor_session(id) ON DELETE SET NULL,
            kind TEXT NOT NULL,
            at TEXT NOT NULL
        );
        CREATE INDEX model_call_at ON model_call(at);
        CREATE INDEX model_call_session ON model_call(session_id, at);
        """,
    ),
]


def apply_migrations(conn: sqlite3.Connection, migrations: list[Migration]) -> list[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row["id"] for row in conn.execute("SELECT id FROM schema_migrations")}
    new: list[str] = []
    for migration in migrations:
        if migration.id in applied:
            continue
        script = (
            "BEGIN IMMEDIATE;\n"
            + migration.sql
            + ";\nINSERT INTO schema_migrations (id, applied_at) VALUES ("
            + _quote(migration.id)
            + ", "
            + _quote(utcnow())
            + ");\nCOMMIT;"
        )
        try:
            conn.executescript(script)
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        new.append(migration.id)
    return new


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
