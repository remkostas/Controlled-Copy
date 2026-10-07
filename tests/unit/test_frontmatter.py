"""FR-SRC-07: front matter parsed into metadata."""

import pytest

from controlled_copy.ingestion.frontmatter import MALFORMED, split_front_matter
from tests.conftest import corpus_file

pytestmark = [pytest.mark.unit, pytest.mark.stage1]


def test_tc_src_008_full_front_matter_is_stored_and_excluded_from_body():
    text = corpus_file("SOP-INB-001_inbound-receiving_rev3.md").decode()
    meta, body, warning = split_front_matter(text)
    assert warning is None
    assert meta == {
        "document_id": "SOP-INB-001",
        "title": "Inbound Receiving Procedure",
        "revision": "3",
        "status": "approved",
        "effective_from": "2026-01-01",
        "site": "HAM-01",
        "process": "inbound_receiving",
        "applicable_roles": ["warehouse_operator", "shift_lead"],
        "owner_role": "process_owner",
        "supersedes": "SOP-INB-001 rev 2",
    }
    assert body.startswith("# SOP-INB-001 Inbound Receiving Procedure (Revision 3)")
    assert "document_id:" not in body and "---" not in body.splitlines()[0]


@pytest.mark.parametrize(
    "text",
    [
        "---\ndocument_id: [unclosed\n---\n# Body\n",  # invalid YAML
        "---\n- just\n- a list\n---\n# Body\n",  # not a mapping
        "---\nbase: &a [x, x]\nmore: *a\n---\n# Body\n",  # anchors and aliases are refused
        "---\ndocument_id: X\n# never closed\n",  # no closing delimiter
    ],
)
def test_tc_src_009_malformed_front_matter_means_no_metadata_with_warning(text):
    meta, body, warning = split_front_matter(text)
    assert meta is None
    assert warning == MALFORMED
    assert "Body" in body or "never closed" in body


def test_tc_src_009_unknown_status_is_normalised():
    meta, _, warning = split_front_matter("---\ndocument_id: D-1\nstatus: Approvedish\n---\ntext\n")
    assert warning is None
    assert meta["status"] == "unknown"


def test_tc_src_009_no_front_matter_is_not_a_warning():
    assert split_front_matter("# Just a heading\n") == (None, "# Just a heading\n", None)
