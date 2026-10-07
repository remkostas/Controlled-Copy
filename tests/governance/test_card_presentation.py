"""FR-GOV-04, FR-GOV-07 presentation: an excluded revision that matched is a quiet note under
Applicability, never a yellow warning above a supported answer; a refused card shows no tables."""

import pytest

from tests.helpers.cards import card_responder, empty_card, passage_with

pytestmark = [pytest.mark.integration, pytest.mark.stage2]

SITUATION = (
    "This quality-managed material comes from a certified supplier. Revision 2 allows direct posting "
    "to unrestricted stock. Can I post it directly?"
)


def supported_card_html(workspace, fake) -> str:
    def build(request):
        pid, quote = passage_with(request, "always posted to quality inspection stock")
        return empty_card(
            required_actions=[
                {
                    "type": "requirement",
                    "text": "Post it to quality inspection stock.",
                    "citations": [{"passage_id": pid, "quote": quote}],
                }
            ]
        )

    fake.responder = card_responder(build)
    return workspace.card(SITUATION, htmx=True).text


def test_tc_gov_004_a_matched_obsolete_revision_is_a_quiet_note_under_applicability(workspace, fake):
    body = supported_card_html(workspace, fake)
    assert "card-result--supported" in body
    note = body.index('class="card-warning"')
    assert note > body.index("<h3>Applicability</h3>"), "the note sits in the Applicability section"
    assert "notice--warn" not in body, "no yellow warning box on a supported card"
    assert "SOP-INB-001 rev 2" in body[note:] and "obsolete" in body[note:]


def test_tc_gov_008_a_refused_card_shows_no_applicability(workspace):
    body = workspace.card("What is the forklift speed limit in the yard?", htmx=True).text
    assert "card-result--refusal" in body
    assert "<h3>Applicability</h3>" not in body
    assert 'class="applicability"' not in body
