"""Verify model quotes against the passages that were actually in the prompt.

A citation survives only if its passage ID was in the prompt and its quote
occurs in that passage. Matching ignores differences in whitespace (including
spaces before punctuation, a common PDF extraction artefact), line-break
hyphenation, typographic quotation marks and dashes, and letter case; it is
otherwise exact. Quotes may skip text with an ellipsis; every fragment must
then occur in order. The verified span is mapped back to exact character
offsets in the source, which the viewer highlights.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Built from code points so no invisible characters live in the source file.
CHAR_MAP = {chr(code): "'" for code in (0x2018, 0x2019, 0x201A, 0x201B, 0x2032, 0x60)}
CHAR_MAP |= {chr(code): '"' for code in (0x201C, 0x201D, 0x201E, 0x201F, 0x2033, 0xAB, 0xBB)}
CHAR_MAP |= {chr(code): "-" for code in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)}
CHAR_MAP[chr(0xA0)] = " "  # no-break space
ELLIPSIS = re.compile(r"\s*(?:\.\.\.|\u2026|\[\.\.\.\]|\[\u2026\])\s*")
EDGE_PUNCTUATION = " \t\n\"'.,;:!?()[]"
SOFT_HYPHEN = chr(0xAD)
HYPHENS = "-" + chr(0x2010) + chr(0x2011)
OPENING = "([{"
CLOSING = ",.;:!?)]}%"
MIN_WORDS = 3
MIN_FRAGMENT_WORDS = 2


@dataclass(frozen=True)
class Match:
    start: int
    end: int


def normalise_with_map(text: str) -> tuple[str, list[int]]:
    """Normalise text and return, for every output character, its index in `text`."""
    out: list[str] = []
    index: list[int] = []
    previous_space = True
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == SOFT_HYPHEN:
            i += 1
            continue
        if ch in HYPHENS and out and out[-1].isalpha():
            # Hyphens inside words are dropped on both sides of the comparison, so
            # "goods-receipt", "goods-<newline>receipt" (a compound broken at a line end)
            # and "ware-<newline>house" (line-break hyphenation) match their quoted forms.
            j = i + 1
            if j < n and text[j] in " \t\n":
                while j < n and text[j] in " \t":
                    j += 1
                if j < n and text[j] == "\n":
                    j += 1
                    while j < n and text[j] in " \t":
                        j += 1
                else:
                    j = -1  # "word - word" or "word- word": a dash between words, keep it
            if 0 < j < n and text[j].isalpha():
                i = j
                continue
        ch = CHAR_MAP.get(ch, ch)
        if ch.isspace():
            if not previous_space and not (out and out[-1] in OPENING):
                out.append(" ")
                index.append(i)
                previous_space = True
            i += 1
            continue
        if ch in CLOSING and out and out[-1] == " ":
            # PDF extraction often puts a space before punctuation ("MEASURE , and").
            out.pop()
            index.pop()
        for part in unicodedata.normalize("NFKC", ch).casefold():
            out.append(part)
            index.append(i)
        previous_space = False
        i += 1
    while out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def normalise(text: str) -> str:
    return normalise_with_map(text)[0]


def _number_continues(haystack: str, at: int, step: int) -> bool:
    """True if a separator at `at` continues a number ("3" inside "3.5", "1" inside "1,200")."""
    beyond = at + step
    return haystack[at] in ".," and 0 <= beyond < len(haystack) and haystack[beyond].isdigit()


def _find_whole_words(haystack: str, needle: str, start: int) -> int:
    """Like str.find, but the match may not start or end in the middle of a word."""
    position = haystack.find(needle, start)
    while position >= 0:
        end = position + len(needle)
        starts_clean = position == 0 or not (
            (needle[0].isalnum() and haystack[position - 1].isalnum())
            or (needle[0].isdigit() and _number_continues(haystack, position - 1, -1))
        )
        ends_clean = end == len(haystack) or not (
            (needle[-1].isalnum() and haystack[end].isalnum())
            or (needle[-1].isdigit() and _number_continues(haystack, end, 1))
        )
        if starts_clean and ends_clean:
            return position
        position = haystack.find(needle, position + 1)
    return -1


def find_quote(passage: str, quote: str) -> Match | None:
    """Find `quote` in `passage`; return offsets within `passage` or None."""
    fragments = [normalise(f).strip(EDGE_PUNCTUATION) for f in ELLIPSIS.split(quote)]
    fragments = [f for f in fragments if f]
    if not fragments:
        return None
    if sum(len(f.split()) for f in fragments) < MIN_WORDS:
        return None
    if len(fragments) > 1 and any(len(f.split()) < MIN_FRAGMENT_WORDS for f in fragments):
        return None
    haystack, index = normalise_with_map(passage)
    cursor = 0
    first_start: int | None = None
    last_end = 0
    for fragment in fragments:
        position = _find_whole_words(haystack, fragment, cursor)
        if position < 0:
            return None
        if first_start is None:
            first_start = position
        last_end = position + len(fragment)
        cursor = last_end
    assert first_start is not None
    return Match(start=index[first_start], end=index[last_end - 1] + 1)
