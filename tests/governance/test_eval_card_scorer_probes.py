"""The scorer's harmful and correct probe cards (second re-check of the full-audit fixes,
R2-EVAL-01): every harmful card must fail, every correct one must pass.

The cards come from both independent re-checks and from two stress sets written to measure the
scorer on wordings it was not tuned on (`scorer_probe_cards.json`). Every quote is a genuine
passage of the demo corpus at its real offsets, so citations verify like real ones. The scorer
is still a word-pattern filter: these cards show what it catches, not that it catches every
harmful wording."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.governance.test_eval_card_scorer import CORPUS, SCORER, case

pytestmark = [pytest.mark.unit, pytest.mark.stage2]

DOCUMENTS = {
    "wi": ("WI-QUA-004 rev 2", "WI-QUA-004_damaged-material_rev2.md"),
    "sop": ("SOP-INB-001 rev 3", "SOP-INB-001_inbound-receiving_rev3.md"),
    "matrix": ("MATRIX-ESC-001 rev 2", "MATRIX-ESC-001_escalation-responsibilities_rev2.md"),
    "guide": ("GUIDE-WMS-003 rev 1", "GUIDE-WMS-003_goods-receipt-errors_rev1.md"),
}
TEXTS = {key: (CORPUS / name).read_text() for key, (_, name) in DOCUMENTS.items()}
QUOTES = {
    "STOP": (
        "wi",
        "If there is a leak, an unknown substance or an unusual odour, stop unloading immediately.",
    ),
    "ISOLATE": ("wi", "Isolate the area, keep other people away and do not touch the material."),
    "NOTIFY": ("wi", "Notify the QA lead and EHS at once."),
    "RESUME": ("wi", "Unloading resumes only after EHS has cleared the area."),
    "WET": (
        "wi",
        "If a seal is broken or the packaging is wet, move the handling unit to the quarantine area Q-01, "
        "post it to blocked stock and notify the QA inspector.",
    ),
    "NOWET": ("wi", "Do not open wet packaging."),
    "QI": (
        "sop",
        "Material that is flagged as quality-managed in the material master is always posted to quality "
        "inspection stock",
    ),
    "CERT": ("sop", "regardless of the supplier's certification status"),
    "GR101": (
        "guide",
        "Action: do not post. Move the handling unit to the over-delivery area OD-01 and inform purchasing.",
    ),
    "NEVER": ("guide", "Never: post against another open line of the same purchase order."),
    "GUIDE_UNKNOWN": (
        "guide",
        "If the code is not listed in this guide, stop and contact the WMS key user (see MATRIX-ESC-001).",
    ),
    "MATRIX_WMS": (
        "matrix",
        "| WMS errors not solved by GUIDE-WMS-003, unknown error codes | WMS key user | 1 hour |",
    ),
}
# What the app would show next to these statements for the cases that need more than a plain
# supported card.
CARD = {
    "E-03": {"status": "expert_confirmation", "undocumented": ["GR-299"]},
    "E-06": {"warnings": [{"label": "SOP-INB-001 rev 2"}]},
}
CARDS = json.loads((Path(__file__).parent / "scorer_probe_cards.json").read_text())


class FakeApp:
    def source_text(self, source_id: str) -> str:
        return TEXTS[source_id]


def body(case_id: str, items: list[list[Any]]) -> dict[str, Any]:
    citations, sections = [], {}
    for section, kind, text, keys in items:
        cites = []
        for key in keys:
            doc, passage = QUOTES[key]
            start = TEXTS[doc].index(passage)
            n = len(citations) + 1
            citations.append(
                {"n": n, "source_id": doc, "start": start, "end": start + len(passage), "quote": passage}
            )
            cites.append({"n": n})
        sections.setdefault(section, []).append({"type": kind, "text": text, "cites": cites})
    cited = {c["source_id"] for c in citations}
    extra = CARD.get(case_id, {})
    return {
        "output": {
            "card": {
                "status": extra.get("status", "supported"),
                "reasons": [],
                "used": [{"source_id": k, "label": DOCUMENTS[k][0]} for k in DOCUMENTS if k in cited],
                "excluded": [],
                "warnings": extra.get("warnings", []),
                "undocumented": extra.get("undocumented", []),
            },
            "sections": [{"key": key, "items": entries} for key, entries in sections.items()],
            "citations": citations,
        }
    }


def score(case_id: str, items: list[list[Any]]) -> list[str]:
    return SCORER.check_card(case(case_id), 200, body(case_id, items), FakeApp(), {})["reasons"]


@pytest.mark.parametrize(("name", "case_id", "items"), CARDS["harmful"], ids=[c[0] for c in CARDS["harmful"]])
def test_tc_eval_014_a_harmful_card_fails(name, case_id, items):
    assert score(case_id, items), f"{name}: the harmful statement passed"


@pytest.mark.parametrize(("name", "case_id", "items"), CARDS["correct"], ids=[c[0] for c in CARDS["correct"]])
def test_tc_eval_015_a_correct_card_passes(name, case_id, items):
    assert score(case_id, items) == [], name
