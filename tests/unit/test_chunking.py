"""FR-IDX-01 and FR-IDX-02: chunks keep their place in the source."""

import pytest

from controlled_copy.ingestion import chunking
from controlled_copy.ingestion.pdf import extract_pdf
from tests.helpers.pdf import make_pdf

pytestmark = [pytest.mark.unit, pytest.mark.stage1]

MARKDOWN = (
    """# Manual

Intro line.

## 1 Scope

Short scope text.

### 1.1 Detail

Detail text here.

## 2 Long section

"""
    + "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(1, 12))
    + "\n"
)


def test_tc_idx_001_markdown_chunks_keep_heading_path_and_exact_offsets():
    chunks = chunking.chunk_markdown(MARKDOWN)
    locators = [c.locator for c in chunks]
    assert "Manual › 1 Scope" in locators
    assert "Manual › 1 Scope › 1.1 Detail" in locators
    long_parts = [c for c in chunks if c.locator.startswith("Manual › 2 Long section")]
    assert len(long_parts) >= 3, "a long section must be split"
    assert all("(part " in c.locator for c in long_parts)
    for chunk in chunks:
        assert MARKDOWN[chunk.char_start : chunk.char_end] == chunk.text
        assert len(chunk.text) <= chunking.MAX_CHARS
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_tc_idx_001_sibling_heading_resets_the_path():
    text = "# A\n\n## B\n\nb text\n\n## C\n\nc text\n"
    locators = [c.locator for c in chunking.chunk_markdown(text)]
    assert "A › C" in locators and "A › B › C" not in locators


def test_tc_idx_001_plain_text_windows_cover_all_paragraphs():
    text = "\n\n".join(f"Para {i} " + "x " * 100 for i in range(10))
    chunks = chunking.chunk_plain(text)
    assert chunks[0].locator.startswith("paragraph")
    joined = " ".join(c.text for c in chunks)
    for i in range(10):
        assert f"Para {i} " in joined
    for chunk in chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text


def test_tc_idx_002_pdf_chunks_carry_their_page():
    pdf = make_pdf(["First page about receiving.", "Second page about putaway.", "Third page about returns."])
    pages = extract_pdf(pdf, max_pages=10, timeout=20)
    text, starts = chunking.join_pages(pages)
    chunks = chunking.chunk_pdf(text, starts)
    assert [c.page for c in chunks] == [1, 2, 3]
    assert [c.locator for c in chunks] == ["page 1", "page 2", "page 3"]
    assert "Second page" in chunks[1].text
    for chunk in chunks:
        assert text[chunk.char_start : chunk.char_end] == chunk.text
