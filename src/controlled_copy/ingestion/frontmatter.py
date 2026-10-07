"""YAML front matter with document-control metadata.

Only known fields are kept and every value becomes a short string (or a list of
strings for roles). Malformed front matter means "no metadata" plus a warning,
never a crash. YAML anchors and aliases are refused, which rules out
alias-expansion ("billion laughs") attacks on `yaml.safe_load`.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

import yaml

FIELDS = (
    "document_id",
    "title",
    "revision",
    "status",
    "effective_from",
    "site",
    "process",
    "applicable_roles",
    "owner_role",
    "supersedes",
)
STATUSES = frozenset({"approved", "draft", "obsolete"})
MAX_FRONT_MATTER = 4000
MAX_VALUE = 200
_ALIAS = re.compile(r"(^|[\s\[{,:-])[&*][A-Za-z0-9_]")
MALFORMED = "The front matter could not be read, so this source has no document metadata."


def _text(value: Any) -> str:
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value).strip()[:MAX_VALUE]


def _normalise(data: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for key in FIELDS:
        if key not in data or data[key] is None:
            continue
        value = data[key]
        if key == "applicable_roles":
            roles = value if isinstance(value, list) else [value]
            meta[key] = [_text(role) for role in roles if role is not None][:20]
        else:
            meta[key] = _text(value)
    status = str(meta.get("status", "")).lower()
    meta["status"] = status if status in STATUSES else "unknown"
    return meta


def split_front_matter(text: str) -> tuple[dict[str, Any] | None, str, str | None]:
    """Return (metadata or None, body, warning or None)."""
    if not text.startswith("---\n"):
        return None, text, None
    end = text.find("\n---", 3)
    if end == -1 or text[end + 4 : end + 5] not in ("\n", ""):
        return None, text, MALFORMED
    raw = text[4:end]
    body = text[end + 4 :].lstrip("\n")
    if len(raw) > MAX_FRONT_MATTER or _ALIAS.search(raw):
        return None, body, MALFORMED
    try:
        data = yaml.safe_load(raw)
    except (yaml.YAMLError, RecursionError):
        # RecursionError: deeply nested lists or maps ("[[[[...") exhaust the parser's stack
        # well below the size limit; that is malformed metadata, not a failed upload.
        return None, body, MALFORMED
    if not isinstance(data, dict):
        return None, body, MALFORMED
    return _normalise(data), body, None


FORM_FIELDS = ("document_id", "revision", "status", "effective_from", "site", "applicable_roles")
_DOCUMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def from_form(fields: dict[str, str | None]) -> dict[str, Any] | None:
    """Document-control metadata typed into the upload form, validated like front matter.

    Returns None when every field is empty (the file's own front matter then applies).
    Raises ValueError with a user-facing message for a value the rules cannot use."""
    values = {key: " ".join((fields.get(key) or "").split()) for key in FORM_FIELDS}
    if not any(values.values()):
        return None
    if values["status"] not in STATUSES:
        raise ValueError("Choose a status for the document: approved, draft or obsolete.")
    if values["document_id"] and not _DOCUMENT_ID.fullmatch(values["document_id"]):
        raise ValueError("Use letters, digits, dots, hyphens or underscores for the document ID.")
    if values["effective_from"]:
        try:
            dt.date.fromisoformat(values["effective_from"])
        except ValueError:
            raise ValueError("Enter the effective date as YYYY-MM-DD.") from None
    data: dict[str, Any] = {key: value for key, value in values.items() if value}
    if "applicable_roles" in data:
        data["applicable_roles"] = [r.strip() for r in data["applicable_roles"].split(",") if r.strip()]
    return _normalise(data)
