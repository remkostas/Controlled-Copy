"""Today's date where the demo's visitors are (Germany), for the chat and the Resolution Card."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    """The current time in UTC; tests replace this to check the date boundaries."""
    return datetime.now(UTC)


def _last_sunday(year: int, month: int) -> datetime:
    """01:00 UTC on the last Sunday of the month: when Central European summer time changes."""
    day = datetime(year, month + 1, 1, 1, tzinfo=UTC) - timedelta(days=1)
    return day - timedelta(days=(day.weekday() + 1) % 7)


def berlin_today(now: datetime | None = None) -> str:
    """Today's date in Germany, where the demo's visitors are. Computed from the EU rule rather
    than a time-zone database, which the slim container image does not guarantee."""
    now = now or utc_now()
    summer = _last_sunday(now.year, 3) <= now < _last_sunday(now.year, 10)
    return (now + timedelta(hours=2 if summer else 1)).date().isoformat()
