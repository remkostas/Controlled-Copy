"""Turn database rows into the plain dictionaries the templates render."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from controlled_copy.answering.citations import short_locator
from controlled_copy.storage.repo import TOMBSTONE

KIND_LABELS = {"pdf": "PDF", "md": "Markdown", "txt": "Text", "paste": "Pasted text"}
ORIGIN_LABELS = {
    "asserted": ("Metadata asserted by uploader", "asserted by uploader"),
    "curated": ("Curated metadata (demo document control)", "curated"),
    "none": ("", "none"),
}
TYPE_LABELS = {
    "requirement": "Requirement",
    "inference": "Inference",
    "recommendation": "Recommendation",
    "missing_evidence": "Missing evidence",
}


def time_label(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M UTC")


def _plural(count: int, noun: str) -> str:
    return f"{count:,} {noun}" + ("" if count == 1 else "s")


def source_view(row: sqlite3.Row, selected: bool = True) -> dict[str, Any]:
    kind = row["kind"]
    keys = row.keys()
    if kind == "pdf":
        size = _plural(int(row["pages"] or 0), "page")
    elif kind == "md" and "section_count" in keys:
        size = _plural(int(row["section_count"] or 0), "section")
    elif "char_count" in keys:
        size = _plural(int(row["char_count"] or 0), "character")
    else:
        size = _plural(int(row["bytes"]), "byte")
    metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else None
    origin_label, origin_short = ORIGIN_LABELS.get(row["metadata_origin"], ("", "none"))
    meta = None
    if metadata:
        meta = {
            "document_id": metadata.get("document_id"),
            "revision": metadata.get("revision"),
            "status": metadata.get("status") or "unknown",
            "effective_from": metadata.get("effective_from"),
            "site": metadata.get("site"),
        }
    return {
        "id": row["id"],
        "title": row["title"],
        "kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind),
        "size_label": size,
        "warnings": json.loads(row["warnings_json"] or "[]"),
        "meta": meta,
        "metadata": metadata or {},
        "origin_label": origin_label,
        "origin_short": origin_short,
        "created_label": time_label(row["created_at"]),
        "superseded_by": None,
        "selected": selected,
    }


def _cite_views(numbers: list[dict[str, Any]], citations: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    views = []
    for ref in numbers:
        c = citations.get(int(ref["n"]))
        if not c:
            continue
        views.append(
            {
                "n": c["n"],
                "url": f"/sources/{c['source_id']}?start={c['start']}&end={c['end']}",
                "label": c["label"],
                "deleted": False,
            }
        )
    return views


def answer_view(answer: dict[str, Any], status: str = "ok") -> dict[str, Any]:
    if status == TOMBSTONE:
        return {"kind": "tombstone"}
    citations = {int(c["n"]): c for c in answer.get("citations", [])}
    statements = [
        {"text": s["text"], "cites": _cite_views(s.get("cites", []), citations)}
        for s in answer.get("statements", [])
    ]
    return {
        "kind": answer.get("kind", "error"),
        "statements": statements,
        "gaps": answer.get("gaps", []),
        "removed": int(answer.get("removed", 0)),
        "cite_count": len(citations),
        "source_count": len({c["source_id"] for c in citations.values()}),
        "searched_sources": int(answer.get("searched_sources", 0)),
        "search_query": answer.get("search_query"),
        "reason": answer.get("reason"),
        "message": answer.get("message", ""),
    }


def error_turn(question: str, message: str) -> dict[str, Any]:
    return {
        "id": "error",
        "question": question,
        "search_query": None,
        "answer": {"kind": "error", "message": message},
    }


def turn_view(
    turn_id: str, question: str, search_query: str | None, answer: dict[str, Any], status: str = "ok"
) -> dict[str, Any]:
    return {
        "id": turn_id,
        "question": question,
        "search_query": search_query,
        "answer": answer_view(answer, status),
    }


def turn_views(messages: list[sqlite3.Row]) -> list[dict[str, Any]]:
    turns: dict[str, dict[str, sqlite3.Row]] = {}
    for row in messages:
        turns.setdefault(row["turn_id"], {})[row["role"]] = row
    views = []
    for turn_id, pair in turns.items():
        user, assistant = pair.get("user"), pair.get("assistant")
        if not user or not assistant:
            continue
        views.append(
            turn_view(
                turn_id,
                user["content"],
                assistant["search_query"],
                json.loads(assistant["content"] or "{}"),
                assistant["status"],
            )
        )
    return views


def output_view(
    row: sqlite3.Row, open_: bool = False, partials: dict[str, str] | None = None
) -> dict[str, Any]:
    created = time_label(row["created_at"])
    output = json.loads(row["output_json"] or "{}")
    base = {"id": row["id"], "open": open_, "removed": 0, "sections": [], "message": "", "partial": None}
    if row["status"] == TOMBSTONE:
        return {**base, "kind": "tombstone", "title": "Studio output removed", "meta_label": created}
    citations = {int(c["n"]): c for c in output.get("citations", [])}
    sections = []
    for section in output.get("sections", []):
        entries = [
            {
                "type": item.get("type"),
                "text": item["text"],
                "type_label": TYPE_LABELS.get(item.get("type") or ""),
                "cites": _cite_views(item.get("cites", []), citations),
            }
            for item in section.get("items", [])
        ]
        sections.append({"title": section["title"], "entries": entries})
    sources = int(output.get("source_count", 0))
    return {
        **base,
        "kind": "ok",
        "title": output.get("title", "Studio output"),
        "meta_label": f"{_plural(sources, 'source')} · {created}",
        "sections": sections,
        "removed": int(output.get("removed", 0)),
        "extra": output,
        "partial": (partials or {}).get(row["template"]),
        "cite_index": citations,
    }


def focus_label_for(
    chunks: list[sqlite3.Row], start: int, title: str, metadata: dict[str, Any] | None
) -> str | None:
    for chunk in chunks:
        if chunk["char_start"] <= start < chunk["char_end"]:
            name = title
            if metadata and metadata.get("document_id"):
                name = metadata["document_id"] + (
                    f" rev {metadata['revision']}" if metadata.get("revision") else ""
                )
            return f"{name} · {short_locator(chunk['locator'])}"
    return None
