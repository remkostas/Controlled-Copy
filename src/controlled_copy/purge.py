"""Retention: delete sessions not seen for RETENTION_HOURS, with everything in them.

Runs hourly inside the app, or once from the command line:
    python -m controlled_copy.purge
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from controlled_copy.config import Settings
from controlled_copy.logs import configure_logging, log_event
from controlled_copy.storage.db import CORE_MIGRATIONS, apply_migrations, connect
from controlled_copy.storage.repo import Repo

ORPHAN_GRACE_SECONDS = 3600


@dataclass(frozen=True)
class PurgeResult:
    sessions: int
    files: int
    orphans: int


def remove_uploads(settings: Settings, names: list[str]) -> None:
    for name in names:
        (settings.uploads_dir / name).unlink(missing_ok=True)


def purge(settings: Settings, repo: Repo, now: datetime | None = None) -> PurgeResult:
    sessions, files = repo.purge_expired(settings.retention_hours, now)
    if sessions:
        repo.checkpoint()
    remove_uploads(settings, files)
    uploads = settings.uploads_dir
    orphans = 0
    if uploads.is_dir():
        referenced = repo.referenced_files()
        cutoff = time.time() - ORPHAN_GRACE_SECONDS
        for path in uploads.iterdir():
            if path.is_file() and path.name not in referenced and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                orphans += 1
    result = PurgeResult(sessions, len(files), orphans)
    log_event("purge", sessions=result.sessions, files=result.files, orphans=result.orphans)
    return result


def main() -> None:
    configure_logging()
    settings = Settings()
    conn = connect(settings.db_path)
    try:
        apply_migrations(conn, CORE_MIGRATIONS)
        purge(settings, Repo(conn), datetime.now(UTC))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
