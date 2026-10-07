"""FR-FUP-04 (New chat; a new topic is searched as asked) and FR-ANS-10 (answers know today's date)."""

from datetime import UTC, datetime

import pytest

from controlled_copy.answering import prompts

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
    visitor.paste("Storage", SOURCE)
    assert "/chat/clear" not in visitor.refresh().page
    visitor.ask("How are pallets wrapped?")
    assert f'hx-post="/notebooks/{visitor.notebook_id}/chat/clear"' in visitor.refresh().page


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
    today = datetime.now(UTC).date().isoformat()
    assert f"Today's date: {today}" in answer_call.user
