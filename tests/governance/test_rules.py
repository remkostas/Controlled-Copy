"""FR-GOV-03, FR-GOV-05, FR-GOV-06, FR-GOV-07: deterministic rules (stage 2, no model)."""

from datetime import date

import pytest

from controlled_copy.governance import rules

pytestmark = [pytest.mark.unit, pytest.mark.stage2]

CONTEXT = rules.Context(site="HAM-01", role="warehouse_operator", as_of=date(2026, 10, 7))


def doc(source_id: str, **meta) -> rules.Document:
    base = {
        "document_id": "SOP-1",
        "revision": "3",
        "status": "approved",
        "effective_from": "2026-01-01",
        "site": "HAM-01",
        "applicable_roles": ["warehouse_operator"],
    }
    base.update(meta)
    return rules.document_from(source_id, f"Doc {source_id}", base, "curated")


def test_tc_gov_003_only_applicable_approved_current_documents_are_authoritative():
    documents = [
        doc("approved"),
        doc("draft", document_id="STD-2", status="draft", effective_from="2026-12-01"),
        doc("obsolete", document_id="OLD-3", status="obsolete"),
        doc("future", document_id="FUT-4", effective_from="2027-01-01"),
        doc("other-site", document_id="STO-5", site="HAM-02"),
        doc("other-role", document_id="QA-6", applicable_roles=["qa_inspector"]),
        doc("older", revision="2"),
        doc("all-sites", document_id="WI-7", site="all", applicable_roles=[]),
        rules.document_from("unknown", "Upload", None, "none"),
    ]
    split = rules.split(documents, CONTEXT)
    assert sorted(split.authoritative_ids()) == ["all-sites", "approved"]
    reasons = {source_id: reason for source_id, (_, reason) in split.excluded.items()}
    assert reasons["draft"].startswith("draft")
    assert reasons["obsolete"] == "obsolete"
    assert reasons["future"] == "not yet effective (from 2027-01-01)"
    assert reasons["other-site"] == "other site (HAM-02)"
    assert reasons["other-role"] == "not for role warehouse_operator"
    assert reasons["older"] == "superseded by SOP-1 rev 3"
    assert reasons["unknown"].startswith("status unknown")


def test_tc_gov_005_identifiers_are_extracted_by_pattern():
    assert rules.identifiers("Error GR-204 while posting per SOP-INB-001 at A-14.") == [
        "GR-204",
        "SOP-INB-001",
        "A-14",
    ]
    assert rules.identifiers("The delivery is damaged and wet.") == []
    texts = {"s1": "GR-204 Quantity above open order quantity", "s2": "nothing"}
    assert rules.documented_in("GR-204", texts) == ["s1"]
    assert rules.documented_in("GR-299", texts) == []
    assert rules.documented_in("GR-20", texts) == [], "a prefix of another code does not count"


def test_tc_gov_007_statement_types_are_enforced():
    authoritative = {"auth"}
    requirement = {"text": "Post to blocked stock.", "type": "requirement"}
    assert rules.apply_type_rules(requirement, ["auth"], authoritative)["type"] == "requirement"
    downgraded = rules.apply_type_rules(requirement, ["excluded"], authoritative)
    assert downgraded["type"] == "inference" and "downgraded" in downgraded
    failed = rules.apply_type_rules(requirement, [], authoritative)
    assert failed["type"] == "missing_evidence"
    assert rules.apply_type_rules({"text": "x", "type": "inference"}, [], authoritative) is None
    assert (
        rules.apply_type_rules({"text": "x", "type": "recommendation"}, [], authoritative)["type"]
        == "recommendation"
    )
    assert (
        rules.apply_type_rules({"text": "x", "type": "made_up"}, ["auth"], authoritative)["type"]
        == "inference"
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        (
            {
                "conflict": True,
                "undocumented": ["GR-299"],
                "authoritative_evidence": 0,
                "only_unknown_sources": True,
                "missing": 2,
            },
            "conflict",
        ),
        (
            {
                "conflict": False,
                "undocumented": ["GR-299"],
                "authoritative_evidence": 3,
                "only_unknown_sources": False,
                "missing": 2,
            },
            "expert_confirmation",
        ),
        (
            {
                "conflict": False,
                "undocumented": [],
                "authoritative_evidence": 0,
                "only_unknown_sources": True,
                "missing": 0,
            },
            "expert_confirmation",
        ),
        (
            {
                "conflict": False,
                "undocumented": [],
                "authoritative_evidence": 0,
                "only_unknown_sources": False,
                "missing": 1,
            },
            "expert_confirmation",
        ),
        (
            {
                "conflict": False,
                "undocumented": [],
                "authoritative_evidence": 2,
                "only_unknown_sources": False,
                "missing": 1,
            },
            "context_incomplete",
        ),
        (
            {
                "conflict": False,
                "undocumented": [],
                "authoritative_evidence": 2,
                "only_unknown_sources": False,
                "missing": 0,
            },
            "supported",
        ),
    ],
)
def test_tc_gov_008_status_follows_the_precedence(kwargs, expected):
    status, reasons = rules.result_status(**kwargs)
    assert status == expected
    assert reasons


def test_tc_gov_005_undocumented_means_a_known_family_without_this_code():
    guide = doc("guide", document_id="GUIDE-1")
    storage = doc("storage", document_id="WI-STO", site="HAM-02")
    upload = rules.document_from("upload", "Supplier note", None, "none")
    result = rules.split([guide, storage, upload], CONTEXT)
    texts = {
        "guide": "GR-204 Quantity above open order quantity. Unknown codes: contact the key user.",
        "storage": "Aisles A-10 to A-20 hold storage class 2 only.",
        "upload": "Delivery note DN-55821 for fasteners.",
    }
    found = ["GR-204", "GR-299", "A-14", "DN-55821", "XY-123"]
    # GR-299: the guide defines GR- codes but not this one. A-14: only a document for another
    # site covers the A- family. DN-55821 appears only in an upload without document control,
    # and no document uses XY- codes, so neither is a code the documents should define.
    assert rules.undocumented(found, texts, result) == ["GR-299", "A-14"]
    assert rules.family("SOP-INB-001") == "SOP-INB" and rules.family("GR-299") == "GR"


def test_tc_gov_005_identifiers_ignore_case():
    assert rules.identifiers("The WMS shows gr-299, then Gr-204 and a-14.") == ["GR-299", "GR-204", "A-14"]
    assert rules.documented_in("GR-204", {"s1": "see gr-204 in the guide"}) == ["s1"]


def test_tc_gov_003_revisions_order_part_by_part():
    assert rules.revision_key("1.10") > rules.revision_key("1.9")
    assert rules.revision_key("B") > rules.revision_key("A")
    assert rules.revision_key("10") > rules.revision_key("9")
    newer = rules.split([doc("old", revision="1.9"), doc("new", revision="1.10")], CONTEXT)
    assert newer.authoritative_ids() == ["new"]
    assert newer.excluded["old"][1] == "superseded by SOP-1 rev 1.10"
    letters = rules.split([doc("a", revision="A"), doc("b", revision="B")], CONTEXT)
    assert letters.authoritative_ids() == ["b"]


def test_tc_gov_003_a_document_without_a_site_applies_to_no_site():
    documents = [
        doc("no-site", document_id="NS-1", site=None),
        doc("blank-site", document_id="NS-2", site="  "),
        doc("lower-case", document_id="LC-3", site="ham-01"),
    ]
    result = rules.split(documents, CONTEXT)
    assert result.authoritative_ids() == ["lower-case"]
    assert result.excluded["no-site"][1] == "no site in document-control metadata"
    assert result.excluded["blank-site"][1] == "no site in document-control metadata"


def test_tc_gov_009_asserted_metadata_never_overrides_a_curated_document():
    curated = doc("curated", revision="3")
    claimed = rules.document_from(
        "upload",
        "Supplier note",
        {
            "document_id": "SOP-1",
            "revision": "4",
            "status": "approved",
            "effective_from": "2026-01-01",
            "site": "all",
        },
        "asserted",
    )
    result = rules.split([curated, claimed], CONTEXT)
    assert result.authoritative_ids() == ["curated"]
    assert result.excluded["upload"][1] == "asserted by uploader, but SOP-1 is a curated controlled document"
    # Without a curated document of that ID, asserted metadata still counts (D-036).
    alone = rules.split([claimed], CONTEXT)
    assert alone.authoritative_ids() == ["upload"]


def test_tc_gov_009_asserted_metadata_cannot_take_a_curated_id_by_spelling_or_context():
    def claim(source_id: str, document_id: str) -> rules.Document:
        meta = {
            "document_id": document_id,
            "revision": "9",
            "status": "approved",
            "effective_from": "2026-01-01",
            "site": "all",
        }
        return rules.document_from(source_id, "Supplier note", meta, "asserted")

    curated = doc("curated", document_id="SOP-INB-001")
    variants = [claim("lower", "sop-inb-001"), claim("dash", "SOP\u2011INB\u2011001 ")]
    result = rules.split([curated, *variants], CONTEXT)
    assert result.authoritative_ids() == ["curated"]
    # The curated revision does not apply here (another site); the upload still may not stand in.
    elsewhere = doc("elsewhere", document_id="SOP-INB-001", site="HAM-02")
    result = rules.split([elsewhere, claim("upload", "SOP-INB-001")], CONTEXT)
    assert result.authoritative_ids() == []
    assert result.excluded["upload"][1].startswith("asserted by uploader")


def test_tc_gov_008_supported_names_unverified_statements():
    status, reasons = rules.result_status(
        conflict=False,
        undocumented=[],
        authoritative_evidence=1,
        only_unknown_sources=False,
        missing=0,
        unverified=1,
    )
    assert status == "supported"
    assert "1 statement without a verified quote marked as missing evidence" in reasons[0]


def test_d039_asserted_metadata_is_not_authoritative_next_to_curated_documents():
    curated = doc("curated", document_id="WI-1", site="all")
    upload = rules.document_from(
        "upload",
        "Supplier note",
        {
            "document_id": "NEW-9",
            "revision": "1",
            "status": "approved",
            "effective_from": "2026-01-01",
            "site": "all",
        },
        "asserted",
    )
    result = rules.split([curated, upload], CONTEXT)
    assert result.authoritative_ids() == ["curated"]
    assert result.excluded["upload"][1] == "asserted by uploader; only curated documents are controlled here"
    assert rules.split([upload], CONTEXT).authoritative_ids() == ["upload"], "alone it still counts (D-036)"


def test_tc_gov_008_supported_on_asserted_metadata_says_so():
    status, reasons = rules.result_status(
        conflict=False,
        undocumented=[],
        authoritative_evidence=1,
        only_unknown_sources=False,
        missing=0,
        asserted_only=True,
    )
    assert status == "supported"
    assert reasons[0] == "the approval of these documents is asserted by the uploader, not checked"


def test_tc_gov_003_revision_prefixes_and_lookalike_ids():
    assert rules.revision_key("Rev 4") < rules.revision_key("5")
    assert rules.revision_key("v1") < rules.revision_key("2")
    assert rules.revision_key("rev. 10") == rules.revision_key("10")
    assert rules.document_key("SOP​-INB-001") == rules.document_key("ＳＯＰ-INB-001") == "sop-inb-001"
