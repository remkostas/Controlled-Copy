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


def test_tc_gov_004_a_refused_card_shows_no_applicability(workspace):
    body = workspace.card("What is the forklift speed limit in the yard?", htmx=True).text
    assert "card-result--refusal" in body
    assert "<h3>Applicability</h3>" not in body
    assert 'class="applicability"' not in body


def test_tc_gov_004_a_document_without_metadata_that_drives_the_status_stays_visible(workspace, db):
    """When the only match is a document without document-control metadata, that is the reason
    for "Expert confirmation required": its passage stays under the status, not a quiet note."""
    workspace.visitor.upload(
        "yard-note.txt",
        b"The zebra crossing paint in the yard is renewed every spring by the facility team.",
        notebook_id=workspace.id,
    )
    note_id = db.execute(
        "SELECT id FROM source WHERE notebook_id = ? AND title LIKE 'yard-note%'", (workspace.id,)
    ).fetchone()[0]
    body = workspace.card(
        "When is the zebra crossing paint in the yard renewed by the facility team?",
        source_ids=[note_id],
        htmx=True,
    ).text
    assert "card-result--expert_confirmation" in body
    box = body.index("notice--warn card-warning card-warning--unknown")
    assert box < body.index("<h3>Situation</h3>"), "the box sits right under the status"
    assert "yard-note" in body[box:] and "status unknown" in body[box:]
    assert "zebra crossing paint" in body[box : body.index("<h3>Situation</h3>")], "its passage is shown"
