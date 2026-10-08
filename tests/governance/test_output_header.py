"""FR-STU-06: a Studio output says what it was asked for, so outputs stay distinguishable (stage 2)."""

import pytest

from controlled_copy.web.views import SUBJECT_CHARS

pytestmark = [pytest.mark.integration, pytest.mark.stage2]


def test_tc_stu_006_the_card_header_shows_the_situation(workspace):
    body = workspace.card("The WMS shows error GR-204 after I scan the delivery.", htmx=True).text
    assert (
        '<span class="output__subject">The WMS shows error GR-204 after I scan the delivery.</span>' in body
    )


def test_tc_stu_006_a_long_situation_is_shortened_in_the_header(workspace):
    situation = "The WMS shows error GR-204 after I scan the delivery. " * 5
    body = workspace.card(situation, htmx=True).text
    subject = body.split('<span class="output__subject">', 1)[1].split("</span>", 1)[0]
    assert len(subject) == SUBJECT_CHARS and subject.endswith("…")
