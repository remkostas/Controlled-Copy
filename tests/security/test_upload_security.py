"""FR-SRC-03, FR-SRC-11: content-based type checks and the PDF time limit."""

import time

import pytest

from controlled_copy.ingestion.pdf import extract_pdf
from controlled_copy.ingestion.validate import IngestError
from tests.helpers.pdf import make_nested_pdf, make_pdf
from tests.helpers.slow import never_finishes

pytestmark = [pytest.mark.security, pytest.mark.stage1]

PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(range(256)) * 4


def test_tc_src_003_binary_renamed_to_pdf_is_rejected_and_nothing_stored(visitor, db, settings):
    response = visitor.upload("invoice.pdf", PNG, expect=415)
    assert "not a valid PDF" in response.json()["error"]
    response = visitor.upload("notes.txt", PNG, expect=415)
    assert db.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 0
    assert list(settings.uploads_dir.iterdir()) == []


def test_tc_src_003_pdf_renamed_to_txt_is_handled_as_pdf(visitor, db):
    visitor.upload("disguised.txt", make_pdf(["Real PDF content about pallet labels."]))
    row = db.execute("SELECT kind, text FROM source").fetchone()
    assert row["kind"] == "pdf"
    assert "pallet labels" in row["text"]


def test_tc_src_003_unsupported_extension_is_rejected(visitor):
    response = visitor.upload("macro.docm", b"plain text pretending", expect=415)
    assert "Unsupported file type" in response.json()["error"]


def test_tc_src_004_text_that_is_not_utf8_is_rejected_with_an_encoding_message(visitor, db):
    latin1 = "Größe der Paletten: maximal 1,2 m Höhe. Prüfung durch QA.".encode("latin-1")
    response = visitor.upload("legacy.txt", latin1, expect=415)
    assert "not UTF-8 encoded" in response.json()["error"]
    assert db.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 0


def test_tc_src_013_pathological_pdf_gives_a_clear_error_and_does_not_hang(visitor, db):
    started = time.monotonic()
    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/sources",
        files={"file": ("nested.pdf", make_nested_pdf())},
        headers=visitor.json_headers(),
    )
    elapsed = time.monotonic() - started
    assert elapsed < 15
    if response.status_code == 201:  # the parser coped; the source must then be usable
        assert response.json()["source_id"]
    else:
        assert response.status_code in (413, 422)
        message = response.json()["error"]
        assert (
            "could not be read" in message
            or "No text could be extracted" in message
            or "took longer" in message
        )


def test_tc_src_013_parser_is_stopped_at_the_time_limit():
    started = time.monotonic()
    with pytest.raises(IngestError) as error:
        extract_pdf(make_pdf(["x"]), max_pages=10, timeout=1.0, extractor=never_finishes)
    elapsed = time.monotonic() - started
    assert "took longer than 1 seconds" in error.value.message
    assert elapsed < 5, f"took {elapsed:.1f}s"
