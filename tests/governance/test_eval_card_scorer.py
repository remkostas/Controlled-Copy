"""The card scorer must reject wrong instructions that carry genuine quotes (full audit EVAL-01).

The scorer lives in eval/ (the app never imports it, TC-SEC-006). These tests load it by path
and feed it hand-made cards whose quotes are real passages of the demo corpus, so they make no
model calls and the citation offsets verify."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.stage2]

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "eval"
CORPUS = ROOT / "demo-data" / "inbound-operations"
DOCUMENTS = {
    "wi": ("WI-QUA-004 rev 2", "WI-QUA-004_damaged-material_rev2.md"),
    "sop": ("SOP-INB-001 rev 3", "SOP-INB-001_inbound-receiving_rev3.md"),
    "sop2": ("SOP-INB-001 rev 2", "SOP-INB-001_inbound-receiving_rev2.md"),
    "matrix": ("MATRIX-ESC-001 rev 2", "MATRIX-ESC-001_escalation-responsibilities_rev2.md"),
    "guide": ("GUIDE-WMS-003 rev 1", "GUIDE-WMS-003_goods-receipt-errors_rev1.md"),
}
TEXTS = {key: (CORPUS / name).read_text() for key, (_, name) in DOCUMENTS.items()}


def load_scorer() -> Any:
    sys.path.insert(0, str(EVAL))
    try:
        spec = importlib.util.spec_from_file_location("run_eval_card_under_test", EVAL / "run_eval.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(EVAL))


SCORER = load_scorer()


def case(case_id: str) -> dict[str, Any]:
    for name in ("cases_governed.json", "cases_governed_holdout.json"):
        for entry in json.loads((EVAL / name).read_text())["cases"]:
            if entry["case_id"] == case_id:
                return entry
    raise KeyError(case_id)


class FakeApp:
    def source_text(self, source_id: str) -> str:
        return TEXTS[source_id]


def card(
    status: str, items: list[tuple[str, str, str, list[tuple[str, str]]]], excluded=()
) -> dict[str, Any]:
    """items: (section, type, text, [(document key, exact passage)]). Every passage must be
    in the document, so its citation verifies like a real one."""
    citations, sections = [], {}
    for section, kind, text, quotes in items:
        cites = []
        for key, passage in quotes:
            start = TEXTS[key].index(passage)
            n = len(citations) + 1
            citations.append(
                {"n": n, "source_id": key, "start": start, "end": start + len(passage), "quote": passage}
            )
            cites.append({"n": n})
        sections.setdefault(section, []).append({"type": kind, "text": text, "cites": cites})
    cited = {c["source_id"] for c in citations}
    authoritative = [k for k in ("wi", "sop", "matrix", "guide") if k in cited and k not in excluded]
    return {
        "output": {
            "card": {
                "status": status,
                "reasons": [],
                "used": [{"source_id": k, "label": DOCUMENTS[k][0]} for k in authoritative],
                "excluded": [
                    {"source_id": k, "label": DOCUMENTS[k][0], "reason": "obsolete"} for k in excluded
                ],
                "warnings": [],
                "undocumented": [],
            },
            "sections": [{"key": key, "items": entries} for key, entries in sections.items()],
            "citations": citations,
        }
    }


def score(case_id: str, body: dict[str, Any]) -> list[str]:
    return SCORER.check_card(case(case_id), 200, body, FakeApp(), {})["reasons"]


NOTIFY = ("wi", "Notify the QA lead and EHS at once.")
STOP = ("wi", "If there is a leak, an unknown substance or an unusual odour, stop unloading immediately.")
ISOLATE = ("wi", "Isolate the area, keep other people away and do not touch the material.")


def test_tc_eval_002_a_harmful_instruction_with_a_genuine_quote_fails():
    """The audit's probe: a real WI-QUA-004 quote next to the opposite instruction."""
    body = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Continue unloading and post the leaking material immediately; do not contact QA or EHS.",
                [NOTIFY],
            )
        ],
    )
    reasons = score("E-12", body)
    assert "does not say: stop unloading" in reasons
    assert "does not say: isolate the area and keep people away" in reasons
    assert "does not say: notify the QA lead" in reasons
    assert "says: keep unloading" in reasons
    assert "says: leave out QA or EHS" in reasons
    assert "says: post the leaking material" in reasons


def test_tc_eval_003_a_notification_without_stop_and_isolate_fails():
    body = card(
        "supported",
        [("required_actions", "requirement", "Notify the QA lead and EHS at once.", [NOTIFY])],
    )
    assert score("E-12", body) == [
        "does not say: stop unloading",
        "does not say: isolate the area and keep people away",
    ]


def test_tc_eval_004_the_right_words_in_the_quote_do_not_count():
    """Every required word is in the quotes; the statement says none of it."""
    body = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Follow section 5 of the work instruction.",
                [STOP, ISOLATE, NOTIFY],
            )
        ],
    )
    reasons = score("E-12", body)
    assert {r for r in reasons if r.startswith("does not say")} == {
        "does not say: stop unloading",
        "does not say: isolate the area and keep people away",
        "does not say: notify the QA lead",
        "does not say: notify EHS",
    }


def test_tc_eval_005_a_requirement_from_a_document_that_does_not_apply_fails():
    """A verified quote from the obsolete revision is not authority for a Requirement."""
    passage = "Deviations of up to 5% of the ordered quantity are posted as counted."
    body = card(
        "supported",
        [("required_actions", "requirement", "Post the 96 units as counted.", [("sop2", passage)])],
        excluded=("sop2",),
    )
    reasons = score("E-01", body)
    assert "1 requirement(s) cite no applicable approved document" in reasons
    assert "does not say: post the counted quantity" in reasons


def test_tc_eval_006_a_correct_card_passes():
    """The wording GPT-6 Luna produced for E-12 on the versioned run of 357b1fb."""
    body = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Stop unloading immediately, isolate the area, keep others away, and do not touch the material.",
                [STOP, ISOLATE],
            ),
            (
                "required_actions",
                "requirement",
                "Notify the QA lead and EHS at once; unloading may resume only after EHS clears the area.",
                [NOTIFY, ("wi", "Unloading resumes only after EHS has cleared the area.")],
            ),
            (
                "escalation",
                "requirement",
                "Escalate suspected contamination, leaks, or unknown substances to the QA lead together with EHS immediately.",
                [
                    (
                        "matrix",
                        "| Suspected contamination, leaks, unknown substances | QA lead together with EHS | Immediately |",
                    )
                ],
            ),
        ],
    )
    assert score("E-12", body) == []


def test_tc_eval_007_a_conflict_must_name_both_instructions():
    one_sided = card(
        "conflict",
        [
            (
                "conflicts",
                "conflict",
                "The documents disagree about damaged packaging.",
                [
                    (
                        "wi",
                        "If the outer packaging is damaged but the product inside is intact, accept the delivery.",
                    ),
                    (
                        "sop",
                        "If the outer packaging of a handling unit shows visible damage, refuse the delivery",
                    ),
                ],
            ),
            (
                "escalation",
                "requirement",
                "Notify the QA inspector.",
                [("wi", "post the goods receipt to blocked stock and notify the QA inspector")],
            ),
        ],
    )
    assert score("E-07", one_sided) == [
        "does not say: the conflict names accepting the delivery",
        "does not say: the conflict names refusing the delivery",
    ]


def test_tc_eval_008_negation_and_document_style_are_read_correctly():
    """Correct wording the first version of the checks misread: "Never:" with a colon,
    a prohibition after the verb, and "rather than"."""
    body = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Quality-managed material is always posted to quality inspection stock rather than unrestricted stock.",
                [
                    (
                        "sop",
                        "Material that is flagged as quality-managed in the material master is always posted to quality inspection stock",
                    )
                ],
            ),
            (
                "required_actions",
                "inference",
                "Direct posting to unrestricted stock is not permitted for this material.",
                [("sop", "regardless of the supplier's certification status")],
            ),
        ],
    )
    # E-06 also expects the warning about the obsolete revision the visitor mentions.
    body["output"]["card"]["warnings"] = [{"label": "SOP-INB-001 rev 2"}]
    assert score("E-06", body) == []
    harmful = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Post it directly to unrestricted stock.",
                [("sop", "Only the QA inspector releases quality inspection stock to unrestricted stock.")],
            )
        ],
    )
    assert "says: post it to unrestricted stock" in score("E-06", harmful)
    # "Never:" as the guide writes it, and a negation that governs "posting" through "by".
    no_post = (
        "Action: do not post. Move the handling unit to the over-delivery area OD-01 and inform purchasing."
    )
    other_line = "Never: post against another open line of the same purchase order."
    bypass = "Never bypass a WMS error by posting against a different purchase order line."
    guide_style = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Do not post. Move it to OD-01 and inform purchasing.",
                [("guide", no_post)],
            ),
            ("required_actions", "requirement", other_line, [("guide", other_line)]),
            (
                "required_actions",
                "requirement",
                "Do not bypass the WMS error by posting against a different purchase order line.",
                [("sop", bypass)],
            ),
        ],
    )
    assert score("H-02", guide_style) == []
    reversed_line = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Do not post. Move it to OD-01 and inform purchasing.",
                [("guide", no_post)],
            ),
            (
                "required_actions",
                "requirement",
                "Post it against another open line of the order.",
                [("guide", other_line)],
            ),
        ],
    )
    assert score("H-02", reversed_line) == ["says: post against another order line"]


def test_tc_eval_009_every_case_file_check_is_well_formed():
    for name in ("cases_governed.json", "cases_governed_holdout.json"):
        for entry in json.loads((EVAL / name).read_text())["cases"]:
            for check in entry.get("must_say", []) + entry.get("must_not_say", []):
                assert set(check) <= {"what", "any", "types"}, (entry["case_id"], check)
                assert check["what"] and check["any"]
                for pattern in check["any"]:
                    re.compile(pattern.replace("{gap}", SCORER.GAP))
            # Every case that expects instructions says which ones.
            if set(entry["expected_status"]) & {"supported", "conflict"}:
                assert entry.get("must_say"), entry["case_id"]


def test_tc_eval_010_an_unrelated_negation_does_not_excuse_a_harmful_instruction():
    """Re-check RCK-02 (Codex): a correct first Requirement, then "Do not document this
    decision, continue unloading and post the leaking carton to unrestricted stock". The
    "do not" belongs to "document", not to the actions after the comma."""
    body = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Stop unloading immediately. Isolate the area and keep people away. Notify the QA lead and EHS at once.",
                [STOP, ISOLATE, NOTIFY],
            ),
            (
                "required_actions",
                "requirement",
                "Do not document this decision, continue unloading and post the leaking carton to unrestricted stock.",
                [NOTIFY],
            ),
        ],
    )
    reasons = score("E-12", body)
    assert "says: keep unloading" in reasons
    assert "says: post the leaking material" in reasons


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (
            "Continue unloading the other cartons as long as the leak is not spreading; "
            "stop unloading only if the smell gets stronger.",
            "says: keep unloading",
        ),
        (
            "Continue unloading the other cartons as long as the leak is not spreading; "
            "stop unloading only if the smell gets stronger.",
            "says: make the stop conditional or later",
        ),
        (
            "No need to wait, keep unloading the truck; stop unloading if the leak gets worse.",
            "says: keep unloading",
        ),
        ("Finish unloading the truck first, then stop unloading at this dock.", "says: keep unloading"),
        ("Notify the QA lead and EHS at the end of the shift.", "says: delay telling QA or EHS"),
    ],
)
def test_tc_eval_011_a_delayed_or_conditional_stop_fails(text, reason):
    """Re-check NEW-3 (the first re-check's probes): harmful wording next to a correct card."""
    body = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Stop unloading immediately. Isolate the area and keep people away. Notify the QA lead and EHS at once.",
                [STOP, ISOLATE, NOTIFY],
            ),
            ("required_actions", "requirement", text, [STOP]),
        ],
    )
    assert reason in score("E-12", body)


def test_tc_eval_012_certification_as_an_exemption_fails():
    rule = (
        "sop",
        "Material that is flagged as quality-managed in the material master is always posted to quality inspection stock",
    )
    body = card(
        "supported",
        [
            (
                "required_actions",
                "requirement",
                "Post it directly to unrestricted stock, because a certified supplier is not subject to inspection.",
                [rule],
            ),
            (
                "required_actions",
                "inference",
                "Quality inspection stock applies only to material from uncertified suppliers.",
                [("sop", "regardless of the supplier's certification status")],
            ),
        ],
    )
    body["output"]["card"]["warnings"] = [{"label": "SOP-INB-001 rev 2"}]
    reasons = score("E-06", body)
    assert "says: post it to unrestricted stock" in reasons
    assert "says: certification exempts the material" in reasons


@pytest.mark.parametrize(
    "first",
    [
        "With no exceptions, stop unloading immediately, isolate the area, keep others away, and do not touch the material.",
        "Do not delay stopping unloading immediately. Isolate the area and keep people away.",
        "Without delay, stop unloading. Isolate the area and keep people away.",
    ],
)
def test_tc_eval_013_words_that_urge_an_action_do_not_cancel_it(first):
    """Re-check RCK-02 and NEW-3: correct cards the first version of the checks rejected."""
    body = card(
        "supported",
        [
            ("required_actions", "requirement", first, [STOP, ISOLATE]),
            ("required_actions", "requirement", "Notify the QA lead and EHS at once.", [NOTIFY]),
        ],
    )
    assert score("E-12", body) == []
