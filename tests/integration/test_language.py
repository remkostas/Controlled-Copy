"""FR-ANS-09, FR-RET-02: documents and questions in a language other than English (here German)."""

import json
from pathlib import Path

import pytest

from controlled_copy.answering import prompts
from controlled_copy.retrieval.search import fts_query, retrieve
from tests.helpers.responders import quote_passage_containing

pytestmark = [pytest.mark.stage1]

BRIEFING = Path(prompts.__file__).resolve().parents[1] / "studio" / "templates" / "briefing.json"
GERMAN = (
    "Größere Abweichungen dürfen erst gebucht werden, wenn der Schichtleiter eine Nachzählung "
    "bestätigt hat. Danach wird die gezählte Menge gebucht, nie die bestellte Menge."
)
OTHER = "Damaged pallets are moved to the blocked area and photographed before the truck leaves."


@pytest.mark.unit
def test_tc_ans_009_no_prompt_fixes_the_answer_language():
    """Answers follow the question; quotes stay as written. The interface stays English."""
    assert "in English" not in prompts.ANSWER_SYSTEM
    assert "language of the question" in prompts.ANSWER_SYSTEM
    assert "language of the latest question" in prompts.REWRITE_SYSTEM
    assert "language of the passages" in prompts.SUGGEST_SYSTEM
    briefing = json.loads(BRIEFING.read_text(encoding="utf-8"))["system"]
    assert "in English" not in briefing
    assert "language of the passages" in briefing


@pytest.mark.unit
def test_tc_ret_002_words_with_umlauts_stay_whole_in_the_search_query():
    terms = fts_query("Größere Abweichungen dürfen erst nach der Nachzählung gebucht werden")
    for word in ("größere", "dürfen", "nachzählung", "abweichungen"):
        assert f'"{word}"' in terms
    for fragment in ("gr", "ere", "rfen", "nachz", "hlung"):
        assert f'"{fragment}"' not in terms


@pytest.mark.integration
def test_tc_ret_002_a_german_word_with_an_umlaut_is_found_by_full_text_search(visitor, services):
    visitor.paste("Wareneingang", GERMAN)
    visitor.paste("Pallets", OTHER)
    result = retrieve(services, visitor.sources, "Wer bestätigt eine Nachzählung?")
    assert result.fts_hits >= 1, "the keyword half of the search must match words with umlauts"
    assert "Nachzählung" in result.passages[0].text


@pytest.mark.integration
def test_tc_ans_009_a_german_question_gets_a_verified_german_answer(visitor, fake):
    visitor.paste("Wareneingang", GERMAN)
    fake.responder = quote_passage_containing(
        "wenn der Schichtleiter eine Nachzählung bestätigt hat",
        "Größere Abweichungen werden erst nach einer bestätigten Nachzählung gebucht.",
    )
    answer = visitor.ask("Wann dürfen größere Abweichungen gebucht werden?").json()["answer"]
    assert answer["kind"] == "answer"
    assert answer["statements"][0]["text"] == (
        "Größere Abweichungen werden erst nach einer bestätigten Nachzählung gebucht."
    )
    assert answer["citations"][0]["quote"] == "wenn der Schichtleiter eine Nachzählung bestätigt hat"
