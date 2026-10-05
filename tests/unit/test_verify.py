"""FR-ANS-02, FR-ANS-03, FR-FUP-03: quote normalisation and citation verification."""

import pytest

from controlled_copy.answering.citations import (
    CitationNumbering,
    CitationOut,
    StatementOut,
    verify_statements,
)
from controlled_copy.answering.verify import find_quote
from controlled_copy.retrieval.search import Passage

pytestmark = [pytest.mark.unit, pytest.mark.stage1]

SOURCE = (
    "Deviations of up to 2% of the ordered quantity or 2 units, whichever is smaller, are posted "
    "as counted with a note in the goods\u00a0receipt. Larger deviations need the shift lead's "
    "confirmation; the ware-\nhouse operator then posts the counted quantity."
)


def passage(text: str = SOURCE, chunk_id: int = 1, start: int = 100) -> Passage:
    return Passage(
        chunk_id,
        "src",
        "Title",
        "md",
        "4.2 Tolerance",
        None,
        start,
        start + len(text),
        text,
        None,
        "none",
        0.9,
        0.1,
    )


def statement(text: str, *citations: tuple[str, str]) -> StatementOut:
    return StatementOut(text=text, citations=[CitationOut(passage_id=p, quote=q) for p, q in citations])


@pytest.mark.parametrize(
    "quote",
    [
        "posted as counted with a note in the goods receipt",  # non-breaking space in the source
        "posted   as counted\nwith a note",  # whitespace differences
        "the warehouse operator then posts",  # hyphenation across a line break
        "need the shift lead’s confirmation",  # typographic apostrophe
        "“Deviations of up to 2% of the ordered quantity”",  # typographic quotation marks
        "DEVIATIONS OF UP TO 2% of the ordered quantity",  # case
        "Deviations of up to 2% ... whichever is smaller",  # ellipsis between verified fragments
    ],
)
def test_tc_ans_002_quote_normalisation_accepts_equivalent_quotes(quote):
    assert find_quote(SOURCE, quote) is not None


def test_tc_ans_002_pdf_spacing_before_punctuation_is_tolerated():
    pdf_text = "the Core is composed of four functions: GOVERN , MAP, MEASURE ,\nand MANAGE . Each of these"
    match = find_quote(pdf_text, "four functions: GOVERN, MAP, MEASURE, and MANAGE.")
    assert match is not None
    assert pdf_text[match.start : match.end] == "four functions: GOVERN , MAP, MEASURE ,\nand MANAGE"
    assert find_quote("see ( Appendix A ) for roles", "see (Appendix A) for roles") is not None


def test_tc_ans_002_offsets_map_back_to_the_exact_source_span():
    match = find_quote(SOURCE, "the warehouse operator then posts")
    assert SOURCE[match.start : match.end] == "the ware-\nhouse operator then posts"


@pytest.mark.parametrize(
    "quote",
    [
        "deviations of up to 5% of the ordered quantity",  # changed number
        "posted as counted",  # boundary: three words pass, two words fail (checked below)
        "eviations of up to 2%",  # starts mid-word
        "the shift lead approves everything",  # not in the passage
        "",
    ],
)
def test_tc_ans_003_wrong_or_weak_quotes_fail(quote):
    if quote == "posted as counted":
        assert find_quote(SOURCE, quote) is not None  # exactly three words: allowed
        assert find_quote(SOURCE, "posted as") is None  # two words: too weak
        return
    assert find_quote(SOURCE, quote) is None


def test_tc_ans_003_invalid_citations_are_removed_and_statement_dropped():
    mapping = {"P1": passage()}
    raw = [
        statement("Supported.", ("P1", "whichever is smaller, are posted as counted")),
        statement("Wrong quote.", ("P1", "deviations of up to 10 units are fine")),
        statement("Unknown passage.", ("P7", "whichever is smaller, are posted as counted")),
        statement(
            "Mixed.", ("P1", "invented words here please"), ("P1", "Larger deviations need the shift lead")
        ),
    ]
    result = verify_statements(raw, mapping, CitationNumbering())
    assert [s["text"] for s in result.statements] == ["Supported.", "Mixed."]
    assert result.removed == 2
    assert result.removed_citations == 3
    assert len(result.statements[1]["cites"]) == 1


def test_tc_ans_003_citation_offsets_are_relative_to_the_source():
    numbering = CitationNumbering()
    verify_statements([statement("x", ("P1", "whichever is smaller"))], {"P1": passage(start=500)}, numbering)
    citation = numbering.flat[0]
    expected = SOURCE.index("whichever is smaller")
    assert (citation["start"], citation["end"]) == (
        500 + expected,
        500 + expected + len("whichever is smaller"),
    )
    assert citation["quote"] == "whichever is smaller"


def test_tc_fup_003_citation_to_a_passage_not_retrieved_now_is_removed():
    # Turn 1 retrieved P1 = the tolerance passage. Turn 2 retrieved a different passage as P1.
    turn_two = {
        "P1": passage(text="Material in quality inspection stock stays in the inspection area.", chunk_id=9)
    }
    raw = [statement("From turn one.", ("P1", "whichever is smaller, are posted as counted"))]
    result = verify_statements(raw, turn_two, CitationNumbering())
    assert result.statements == []
    assert result.removed == 1


def test_tc_ans_002_compound_word_broken_at_a_line_end_still_verifies():
    text = "Book the goods-\nreceipt in the WMS before putaway."
    match = find_quote(text, "Book the goods-receipt in the WMS")
    assert match is not None and text[match.start : match.end] == "Book the goods-\nreceipt in the WMS"
    assert find_quote("a goods - receipt split by spaces", "a goods receipt split") is None


def test_tc_ans_003_a_number_cannot_verify_inside_a_longer_number():
    text = "The value is 3.5 kg per pallet and the order has 1,200 units in rev 1.2."
    assert find_quote(text, "value is 3") is None
    assert find_quote(text, "value is 3.5 kg") is not None
    assert find_quote(text, "the order has 1") is None
    assert find_quote(text, "units in rev 1") is None
    assert find_quote(text, "units in rev 1.2") is not None


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        ("Store at -5 degrees Celsius or colder.", "5 degrees Celsius or colder"),
        ("Store at −5 degrees Celsius or colder.", "5 degrees Celsius or colder"),
        ("Gap ±5 mm on every side.", "5 mm on every side"),
        ("Maximum load is 1 200 kg per pallet.", "Maximum load is 1"),
        ("Maximum load is 1'200 kg per pallet.", "Maximum load is 1"),
        ("Recheck after 4/8 hours have passed.", "Recheck after 4"),
        ("Maximum load is 10² kg per pallet.", "Maximum load is 102 kg"),
    ],
)
def test_tc_ans_003_signed_grouped_or_superscript_numbers_cannot_be_cut(text, quote):
    assert find_quote(text, quote) is None


def test_tc_ans_002_en_dash_inside_a_word_matches_a_hyphen():
    assert find_quote("The pre–approved supplier list applies.", "The pre-approved supplier list") is not None
    assert find_quote("Store at -5 degrees Celsius or colder.", "-5 degrees Celsius or colder") is not None
