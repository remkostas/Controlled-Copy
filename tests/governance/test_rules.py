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
