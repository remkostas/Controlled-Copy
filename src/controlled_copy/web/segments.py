"""Split a source's extracted text into renderable segments for the viewer.

The viewer shows exactly the stored text. Segments only add presentation:
heading classes for Markdown lines, page labels for PDFs and a highlight for
the cited passage. Every character of the text appears exactly once, in order.
"""

from __future__ import annotations

from dataclasses import dataclass

_HEADING_CLASSES = {1: "ln--h1", 2: "ln--h2", 3: "ln--h3", 4: "ln--h4"}


@dataclass(frozen=True)
class Segment:
    text: str
    mark: bool = False
    anchor: bool = False
    cls: str = ""
    page_label: str | None = None


def _heading_class(line: str) -> str:
    stripped = line.lstrip()
    level = len(stripped) - len(stripped.lstrip("#"))
    if 1 <= level <= 6 and stripped[level : level + 1] == " ":
        return _HEADING_CLASSES.get(level, "ln--h4")
    return ""


def build_segments(
    text: str,
    highlight: tuple[int, int] | None = None,
    page_starts: list[int] | None = None,
    markdown: bool = False,
) -> list[Segment]:
    if highlight is not None:
        start, end = highlight
        if not (0 <= start < end <= len(text)):
            highlight = None
    starts = sorted(page_starts or [])
    segments: list[Segment] = []
    position = 0
    page_index = 0
    anchored = False
    for line in text.splitlines(keepends=True) or [""]:
        line_start, line_end = position, position + len(line)
        labels = []
        while page_index < len(starts) and starts[page_index] <= line_start:
            page_index += 1
            labels.append(f"Page {page_index}")
        page_label = " · ".join(labels) if labels else None
        cls = _heading_class(line) if markdown else ""
        pieces: list[tuple[str, bool]]
        if highlight and highlight[0] < line_end and highlight[1] > line_start:
            mark_start, mark_end = max(line_start, highlight[0]), min(line_end, highlight[1])
            pieces = []
            if mark_start > line_start:
                pieces.append((text[line_start:mark_start], False))
            pieces.append((text[mark_start:mark_end], True))
            if mark_end < line_end:
                pieces.append((text[mark_end:line_end], False))
        else:
            pieces = [(line, False)]
        for index, (piece, marked) in enumerate(pieces):
            segments.append(
                Segment(
                    text=piece,
                    mark=marked,
                    anchor=marked and not anchored,
                    cls=cls,
                    page_label=page_label if index == 0 else None,
                )
            )
            anchored = anchored or marked
        position = line_end
    return segments
