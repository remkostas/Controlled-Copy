"""Rate limits and the model-call budget.

- Access-code attempts: counted per client IP in memory (no IPs on disk).
- Model calls: every provider call is recorded in the database (session ID,
  kind, time, no content). A visitor may make `model_calls_per_visitor_hour`
  calls per hour; all visitors together `model_calls_per_day` per UTC day, after
  which the app is read-only until midnight UTC.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from controlled_copy.config import Settings
from controlled_copy.errors import UserFacingError
from controlled_copy.storage.db import transaction
from controlled_copy.storage.repo import Repo


class LimitExceeded(UserFacingError):
    """A model-call budget is used up."""


VISITOR_LIMIT_MESSAGE = (
    "You have reached the limit of {limit} model calls per hour for this demo. Please try again later."
)
DAILY_LIMIT_MESSAGE = (
    "The demo has reached its daily budget for model calls. Viewing still works; "
    "questions, uploads and Studio are paused until midnight UTC."
)


class AccessLimiter:
    """Failed access-code attempts per client address, in memory and bounded in size."""

    MAX_TRACKED = 10_000

    def __init__(self, attempts_per_hour: int, window_seconds: float = 3600.0) -> None:
        self.limit = attempts_per_hour
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float] | None:
        entries = self._failures.get(key)
        if entries is None:
            return None
        while entries and now - entries[0] > self.window:
            entries.popleft()
        if not entries:
            del self._failures[key]
            return None
        return entries

    def blocked(self, key: str) -> bool:
        with self._lock:
            entries = self._prune(key, time.monotonic())
            return entries is not None and len(entries) >= self.limit

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            if key not in self._failures and len(self._failures) >= self.MAX_TRACKED:
                for stale in [k for k in self._failures if now - self._failures[k][-1] > self.window]:
                    del self._failures[stale]
                if len(self._failures) >= self.MAX_TRACKED:
                    oldest = min(self._failures, key=lambda k: self._failures[k][-1])
                    del self._failures[oldest]
            self._failures[key].append(now)


class Budget:
    def __init__(self, settings: Settings, repo: Repo) -> None:
        self.settings = settings
        self.repo = repo

    @staticmethod
    def _day_start(now: datetime) -> str:
        return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")

    def read_only(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return self.repo.count_model_calls(self._day_start(now)) >= self.settings.model_calls_per_day

    def check(self, sid: str | None, calls: int = 1) -> None:
        """Raise LimitExceeded if `calls` more model calls would exceed a limit."""
        now = datetime.now(UTC)
        if self.repo.count_model_calls(self._day_start(now)) + calls > self.settings.model_calls_per_day:
            raise LimitExceeded(DAILY_LIMIT_MESSAGE, 503)
        if sid is not None:
            hour_ago = (now - timedelta(hours=1)).isoformat(timespec="seconds")
            limit = self.settings.model_calls_per_visitor_hour
            if self.repo.count_model_calls(hour_ago, sid) + calls > limit:
                raise LimitExceeded(VISITOR_LIMIT_MESSAGE.format(limit=limit), 429)

    def consume(self, sid: str | None, kind: str) -> None:
        """Check and record one call atomically, so parallel requests cannot overshoot."""
        with transaction(self.repo.conn):
            self.check(sid)
            self.repo.record_model_call(sid, kind)
