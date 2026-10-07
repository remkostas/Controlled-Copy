"""The evaluation scorer must reject wrong answers whose quotes are genuine (full audit EVAL-01).

The scorer lives in eval/ (the app never imports it, TC-SEC-006); these tests load it by path
and feed it hand-made responses, so they make no model calls."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.stage1]

EVAL = Path(__file__).resolve().parents[2] / "eval"


def load_scorer() -> Any:
    sys.path.insert(0, str(EVAL))
    try:
        spec = importlib.util.spec_from_file_location("run_eval_under_test", EVAL / "run_eval.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(EVAL))


SOURCE = "The AI RMF Core is composed of four functions: GOVERN, MAP, MEASURE, and MANAGE."


class FakeApp:
    def source_text(self, source_id: str) -> str:
        return SOURCE


def answer(statement: str) -> dict[str, Any]:
    return {
        "answer": {
            "kind": "answer",
            "statements": [{"text": statement}],
            "citations": [
                {
                    "n": 1,
                    "source_id": "s1",
                    "label": "page 8",
                    "start": 0,
                    "end": len(SOURCE),
                    "quote": SOURCE,
                }
            ],
        }
    }


CASE = {
    "kind": "answer",
    "expected_pages": [8],
    "keywords": ["govern", "map", "measure", "manage"],
    "min_keywords": 4,
}


def test_tc_eval_001_terms_only_in_the_quote_do_not_pass():
    scorer = load_scorer()
    wrong = scorer.check_answer(
        CASE, 200, answer("The Core has two parts: planning and reporting."), FakeApp(), {}
    )
    assert wrong["reasons"] == ["only 0 of 4 required terms present"]
    right = scorer.check_answer(
        CASE, 200, answer("The four functions are Govern, Map, Measure and Manage."), FakeApp(), {}
    )
    assert right["reasons"] == []
    # The full answer is kept for a human read.
    assert right["said"] == ["The four functions are Govern, Map, Measure and Manage."]
    assert right["quotes"][0]["quote"] == SOURCE
