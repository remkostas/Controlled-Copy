"""Split extracted text into passages that keep their place in the source.

Every chunk carries `char_start` and `char_end` such that
`text[char_start:char_end] == chunk.text` holds exactly, so a citation can be
highlighted in the viewer at the right place.

- Markdown: one chunk per heading section; the locator is the heading path.
  Long sections are split into paragraph windows.
- PDF: per page, then paragraph windows; the locator is the page.
- Plain text and pasted text: paragraph windows; the locator names the paragraphs.
"""

from __future__ import annotations

import re

from controlled_copy.storage.repo import ChunkRecord as Chunk

TARGET_CHARS = 900
MAX_CHARS = 1400

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$", re.M)
_BLANK_LINE = re.compile(r"\n[ \t]*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+")


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _paragraph_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    for match in _BLANK_LINE.finditer(text, start, end):
        p_start, p_end = _trim(text, cursor, match.start())
        if p_end > p_start:
            spans.append((p_start, p_end))
        cursor = match.end()
    p_start, p_end = _trim(text, cursor, end)
    if p_end > p_start:
        spans.append((p_start, p_end))
    return spans


def _split_long(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split one long paragraph at sentence ends, then at spaces, into pieces <= MAX_CHARS."""
    pieces: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > MAX_CHARS:
        window_end = cursor + MAX_CHARS
        cut = None
        for match in _SENTENCE_END.finditer(text, cursor + TARGET_CHARS // 2, window_end):
            cut = match.start()
        if cut is None:
            space = text.rfind(" ", cursor + TARGET_CHARS // 2, window_end)
            cut = space if space > cursor else window_end
        piece_start, piece_end = _trim(text, cursor, cut)
        if piece_end > piece_start:
            pieces.append((piece_start, piece_end))
        cursor = cut
    piece_start, piece_end = _trim(text, cursor, end)
    if piece_end > piece_start:
        pieces.append((piece_start, piece_end))
    return pieces


def _windows(text: str, start: int, end: int) -> list[tuple[int, int, int, int]]:
    """Group paragraphs into windows. Returns (start, end, first_par, last_par), 1-based paragraphs."""
    units: list[tuple[int, int, int]] = []
    for number, (p_start, p_end) in enumerate(_paragraph_spans(text, start, end), start=1):
        if p_end - p_start > MAX_CHARS:
            units.extend((s, e, number) for s, e in _split_long(text, p_start, p_end))
        else:
            units.append((p_start, p_end, number))
    windows: list[tuple[int, int, int, int]] = []
    current: list[tuple[int, int, int]] = []
    for unit in units:
        if current and unit[1] - current[0][0] > TARGET_CHARS:
            windows.append((current[0][0], current[-1][1], current[0][2], current[-1][2]))
            current = []
        current.append(unit)
    if current:
        windows.append((current[0][0], current[-1][1], current[0][2], current[-1][2]))
    return windows


def chunk_markdown(text: str) -> list[Chunk]:
    headings = [(m.start(), len(m.group(1)), m.group(2).strip()) for m in _HEADING.finditer(text)]
    boundaries = [(0, 0, ""), *headings]
    chunks: list[Chunk] = []
    stack: list[tuple[int, str]] = []
    for index, (start, level, title) in enumerate(boundaries):
        end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(text)
        if level:
            stack = [(lvl, t) for lvl, t in stack if lvl < level]
            stack.append((level, title))
        path = " › ".join(t for _, t in stack) or "Beginning"
        s, e = _trim(text, start, end)
        if e <= s:
            continue
        spans = [(s, e)] if e - s <= MAX_CHARS else [(w[0], w[1]) for w in _windows(text, s, e)]
        for part, (c_start, c_end) in enumerate(spans, start=1):
            locator = path if len(spans) == 1 else f"{path} (part {part})"
            chunks.append(Chunk(len(chunks), locator, None, c_start, c_end, text[c_start:c_end]))
    return chunks


def chunk_plain(text: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for start, end, first, last in _windows(text, 0, len(text)):
        locator = f"paragraph {first}" if first == last else f"paragraphs {first}–{last}"
        chunks.append(Chunk(len(chunks), locator, None, start, end, text[start:end]))
    return chunks


def join_pages(pages: list[str]) -> tuple[str, list[int]]:
    """Join page texts with a blank line; return the full text and each page's start offset."""
    starts: list[int] = []
    parts: list[str] = []
    position = 0
    for index, page in enumerate(pages):
        if index:
            parts.append("\n\n")
            position += 2
        starts.append(position)
        cleaned = page.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
        parts.append(cleaned)
        position += len(cleaned)
    return "".join(parts), starts


def chunk_pdf(full_text: str, page_starts: list[int]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for index, start in enumerate(page_starts):
        end = page_starts[index + 1] - 2 if index + 1 < len(page_starts) else len(full_text)
        for w_start, w_end, _, _ in _windows(full_text, start, end):
            chunks.append(
                Chunk(len(chunks), f"page {index + 1}", index + 1, w_start, w_end, full_text[w_start:w_end])
            )
    return chunks
