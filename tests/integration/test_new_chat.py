"""FR-FUP-04 (New chat; a new topic is searched as asked) and FR-ANS-10 (answers know today's date)."""

from datetime import UTC, datetime

import pytest

from controlled_copy.answering import prompts
from controlled_copy.answering.answer import berlin_today
from controlled_copy.providers.fake import default_responder
from controlled_copy.storage.repo import Repo

pytestmark = [pytest.mark.stage1]

SOURCE = "Pallets are wrapped twice in foil before storage. Damaged pallets go to the blocked area."


def chat_rows(db, notebook_id: str) -> int:
    return db.execute("SELECT COUNT(*) FROM chat_message WHERE notebook_id = ?", (notebook_id,)).fetchone()[0]


@pytest.mark.integration
def test_tc_fup_004_new_chat_removes_the_turns_and_the_next_question_stands_alone(visitor, fake, db):
    visitor.paste("Storage", SOURCE)
    visitor.ask("How are pallets wrapped?")
    visitor.ask("And damaged ones?")
    assert any(call.schema_name == "rewrite" for call in fake.chat_calls), "a follow-up is rewritten"
    assert chat_rows(db, visitor.notebook_id) == 4

    response = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/chat/clear", headers=visitor.json_headers()
    )
    assert response.status_code == 200
    assert response.json() == {"cleared": 4}
    assert chat_rows(db, visitor.notebook_id) == 0
    assert (
        db.execute("SELECT COUNT(*) FROM source WHERE notebook_id = ?", (visitor.notebook_id,)).fetchone()[0]
        == 1
    )

    calls_before = len(fake.chat_calls)
    visitor.ask("Where do damaged pallets go?")
    assert all(call.schema_name != "rewrite" for call in fake.chat_calls[calls_before:]), (
        "after New chat there is no earlier turn to rewrite with"
    )


@pytest.mark.integration
def test_tc_fup_004_new_chat_is_offered_once_there_is_a_chat(visitor):
    # Rendered hidden on an empty chat; the page script shows it after the first answer
    # (browser test in tests/e2e/test_new_chat.py), and a reload shows it straight away.
    visitor.paste("Storage", SOURCE)
    assert 'id="new-chat"' in visitor.refresh().page
    assert " hidden>" in visitor.page.split('id="new-chat"', 1)[1].split("</button>", 1)[0]
    visitor.ask("How are pallets wrapped?")
    button = visitor.refresh().page.split('id="new-chat"', 1)[1].split("</button>", 1)[0]
    assert f'hx-post="/notebooks/{visitor.notebook_id}/chat/clear"' in visitor.page
    assert " hidden>" not in button


@pytest.mark.integration
def test_tc_fup_004_an_answer_still_running_during_new_chat_is_not_stored(visitor, fake, db):
    visitor.paste("Storage", SOURCE)
    visitor.ask("How are pallets wrapped?")
    session_id = db.execute(
        "SELECT session_id FROM notebook WHERE id = ?", (visitor.notebook_id,)
    ).fetchone()[0]
    repo = Repo(db)
    notebook = repo.get_notebook(session_id, visitor.notebook_id)

    def clear_while_answering(request):
        if request.schema_name == "answer":
            repo.clear_chat(notebook)  # the visitor presses New chat while this answer is generated
        return default_responder(request)

    fake.responder = clear_while_answering
    assert visitor.ask("And damaged ones?").status_code == 200
    assert chat_rows(db, visitor.notebook_id) == 0, "the old conversation must not come back"

    fake.responder = default_responder
    calls_before = len(fake.chat_calls)
    visitor.ask("Where do damaged pallets go?")
    assert chat_rows(db, visitor.notebook_id) == 2
    assert all(call.schema_name != "rewrite" for call in fake.chat_calls[calls_before:])


@pytest.mark.integration
def test_tc_fup_004_another_visitor_cannot_clear_the_chat(make_visitor, db):
    alice, bob = make_visitor(), make_visitor()
    alice.paste("Storage", SOURCE)
    alice.ask("How are pallets wrapped?")
    response = bob.client.post(f"/notebooks/{alice.notebook_id}/chat/clear", headers=bob.json_headers())
    assert response.status_code == 404
    assert chat_rows(db, alice.notebook_id) == 2


@pytest.mark.unit
def test_tc_fup_004_the_rewrite_keeps_a_new_topic_as_asked():
    assert "starts a new topic" in prompts.REWRITE_SYSTEM
    assert "never add topics from earlier turns" in prompts.REWRITE_SYSTEM


@pytest.mark.integration
def test_tc_ans_010_answers_are_given_todays_date(visitor, fake):
    visitor.paste("Storage", SOURCE)
    visitor.ask("How are pallets wrapped?")
    answer_call = next(call for call in fake.chat_calls if call.schema_name == "answer")
    assert f"Today's date: {berlin_today()}" in answer_call.user
    assert "not evidence" in prompts.ANSWER_SYSTEM


@pytest.mark.unit
@pytest.mark.parametrize(
    ("utc", "expected"),
    [
        ("2026-10-07T22:30:00", "2026-10-08"),  # summer time: UTC+2, already tomorrow in Berlin
        ("2026-10-07T21:30:00", "2026-10-07"),
        ("2026-12-31T23:30:00", "2027-01-01"),  # winter time: UTC+1
        ("2026-12-31T22:30:00", "2026-12-31"),
        ("2026-03-29T00:59:00", "2026-03-29"),  # before the switch to summer time (01:00 UTC)
        ("2026-03-29T22:30:00", "2026-03-30"),  # after it
        ("2026-10-25T00:59:00", "2026-10-25"),  # summer time ends at 01:00 UTC on Oct 25
        ("2026-10-25T22:30:00", "2026-10-25"),  # winter time again: 23:30 in Berlin
    ],
)
def test_tc_ans_010_today_is_the_date_in_germany(utc, expected):
    assert berlin_today(datetime.fromisoformat(utc).replace(tzinfo=UTC)) == expected
