"""FR-META-01: document-control metadata typed into the upload form (stage 3)."""

import pytest

from controlled_copy.ingestion.frontmatter import from_form

pytestmark = [pytest.mark.unit, pytest.mark.stage3]


def test_tc_meta_001_empty_form_means_the_file_decides():
    assert from_form({}) is None
    assert from_form({"document_id": "  ", "status": ""}) is None


def test_tc_meta_001_values_are_normalised_like_front_matter():
    meta = from_form(
        {
            "document_id": "SOP-INB-002",
            "revision": " 3 ",
            "status": "approved",
            "effective_from": "2026-01-01",
            "site": "HAM-01",
            "applicable_roles": "warehouse_operator, shift_lead,",
        }
    )
    assert meta == {
        "document_id": "SOP-INB-002",
        "revision": "3",
        "status": "approved",
        "effective_from": "2026-01-01",
        "site": "HAM-01",
        "applicable_roles": ["warehouse_operator", "shift_lead"],
    }


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"document_id": "SOP-1"}, "Choose a status"),
        ({"status": "released"}, "Choose a status"),
        ({"status": "approved", "effective_from": "01.01.2026"}, "YYYY-MM-DD"),
        ({"status": "approved", "document_id": "SOP 1; DROP"}, "document ID"),
    ],
)
def test_tc_meta_001_unusable_values_are_refused(fields, message):
    with pytest.raises(ValueError, match=message):
        from_form(fields)
