"""Structured logging without content.

`log_event` writes one JSON line per event. Numbers and booleans pass through;
strings pass only for keys on an allowlist (IDs, model names, kinds, status
codes); session IDs are hashed. Any other string is replaced by its length, so a question, a passage or
an answer cannot reach the logs by accident (security plan S-04, TC-LOG-001).
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from typing import Any

LOGGER_NAME = "controlled_copy"
logger = logging.getLogger(LOGGER_NAME)

STRING_KEYS = frozenset(
    {
        "event",
        "session",
        "notebook",
        "source",
        "output",
        "turn",
        "kind",
        "model",
        "provider",
        "status",
        "error_type",
        "path",
        "method",
        "template",
        "outcome",
        "mode",
    }
)
MAX_STRING = 80


def _clean(key: str, value: Any) -> Any:
    if key == "session" and isinstance(value, str):
        # The session ID is half of the cookie credential: log a short hash instead.
        return hashlib.sha256(value.encode()).hexdigest()[:12]
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str) and key in STRING_KEYS:
        return value[:MAX_STRING]
    if isinstance(value, str):
        return f"<{len(value)} chars>"
    if isinstance(value, list | tuple):
        return f"<{len(value)} items>"
    return f"<{type(value).__name__}>"


def log_event(event: str, **fields: Any) -> None:
    record = {"event": event}
    record.update({key: _clean(key, value) for key, value in fields.items()})
    logger.info(json.dumps(record, sort_keys=True))


def configure_logging(debug: bool = False) -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = True
