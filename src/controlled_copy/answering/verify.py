"""Verify model quotes against the passages that were actually in the prompt.

A citation survives only if its passage ID was in the prompt and its quote
occurs in that passage. Matching ignores differences in whitespace, line-break
hyphenation, typographic quotation marks and dashes, and letter case; it is
otherwise exact. Quotes may skip text with an ellipsis; every fragment must
then occur in order. The verified span is mapped back to exact character
offsets in the source, which the viewer highlights.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

CHAR_MAP = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "′": "'",
    "`": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "″": '"',
    "«": '"',
    "»": '"',
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
    " ": " ",
}
ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\]|\[…\])\s*")
EDGE_PUNCTUATION = " \t\n\"'.,;:!?()[]"
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
        if ch == "­":  # soft hyphen
            i += 1
            continue
        if ch in "-‐‑" and i > 0 and text[i - 1].isalpha():
            j = i + 1
            while j < n and text[j] in " \t":
                j += 1
            if j < n and text[j] == "\n":
                j += 1
                while j < n and text[j] in " \t":
                    j += 1
                if j < n and text[j].isalpha():
                    i = j  # join a word hyphenated across a line break
                    continue
        ch = CHAR_MAP.get(ch, ch)
        if ch.isspace():
            if not previous_space:
                out.append(" ")
                index.append(i)
                previous_space = True
            i += 1
            continue
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


def _find_whole_words(haystack: str, needle: str, start: int) -> int:
    """Like str.find, but the match may not start or end in the middle of a word."""
    position = haystack.find(needle, start)
    while position >= 0:
        end = position + len(needle)
        starts_clean = position == 0 or not (needle[0].isalnum() and haystack[position - 1].isalnum())
        ends_clean = end == len(haystack) or not (needle[-1].isalnum() and haystack[end].isalnum())
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
