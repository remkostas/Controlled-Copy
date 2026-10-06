"""Studio outputs as Markdown, for "Copy as Markdown" and "Download .md".

Every statement keeps its citation numbers, and every number is listed with its source
label and the exact verified quote, so the copy can be checked without the app.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from typing import Any

from controlled_copy.web.views import TYPE_LABELS, model_label, time_label


def clean(text: Any) -> str:
    """One line of plain text: no line breaks that would break a list item or table row."""
    return " ".join(str(text or "").split())


def cell(text: Any) -> str:
    return clean(text).replace("|", "\\|")


def table(header: Iterable[str], rows: Iterable[Iterable[Any]]) -> list[str]:
    head = list(header)
    lines = ["| " + " | ".join(head) + " |", "|" + " :--- |" * len(head)]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in rows]
    return lines


def item_line(item: dict[str, Any]) -> str:
    label = TYPE_LABELS.get(item.get("type") or "")
    cites = "".join(f" [{int(c['n'])}]" for c in item.get("cites", []))
    prefix = f"**{label}:** " if label else ""
    return f"- {prefix}{clean(item.get('text'))}{cites}"


def sections_md(output: dict[str, Any], empty: str | None = None) -> list[str]:
    lines: list[str] = []
    for section in output.get("sections", []):
        items = section.get("items", [])
        if not items and empty is None:
            continue
        lines += ["", f"## {clean(section.get('title'))}", ""]
        lines += [item_line(item) for item in items] or [empty or ""]
    return lines


def citations_md(output: dict[str, Any]) -> list[str]:
    citations = output.get("citations", [])
    if not citations:
        return []
    lines = ["", "## Sources", ""]
    lines += [f'[{int(c["n"])}] {clean(c.get("label"))}: "{clean(c.get("quote"))}"' for c in citations]
    return lines


def footer_md(output: dict[str, Any], created_at: str) -> list[str]:
    parts = [model_label(output.get("model"), bool(output.get("fallback"))), time_label(created_at)]
    note = "Made with Controlled Copy. " + " · ".join(p for p in parts if p)
    removed = int(output.get("removed", 0))
    lines = ["", "---", ""]
    if removed:
        lines.append(f"{removed} statement(s) removed because the quote could not be verified.  ")
    return [*lines, note]


def generic_markdown(output: dict[str, Any], created_at: str) -> str:
    lines = [f"# {clean(output.get('title', 'Studio output'))}"]
    lines += sections_md(output, empty="Nothing in the selected sources supports this section.")
    lines += citations_md(output)
    lines += footer_md(output, created_at)
    return "\n".join(lines).strip() + "\n"


def output_markdown(row: sqlite3.Row, renderers: dict[str, Any], core_ids: Iterable[str]) -> str | None:
    """Markdown for a stored output, or None when it is removed or its layer is switched off."""
    if row["status"] != "ok":
        return None
    output = json.loads(row["output_json"] or "{}")
    template = row["template"]
    if template in renderers:
        return str(renderers[template](output, row["created_at"]))
    if template in set(core_ids):
        return generic_markdown(output, row["created_at"])
    return None
