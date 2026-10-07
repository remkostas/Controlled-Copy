"""FR-FUP-04 in a real browser: New chat appears with the first answer, no reload (stage 1)."""

import pytest

from tests.e2e.test_journey_a import SOP, ask, login, upload

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


def test_tc_fup_004_new_chat_appears_after_the_first_answer(page, server_url):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    assert not page.locator("#new-chat").is_visible(), "nothing to start over from yet"
    ask(page, "What is the purpose of the inbound receiving procedure?")
    new_chat = page.locator("#new-chat")
    new_chat.wait_for(state="visible")
    with page.expect_navigation():
        new_chat.click()  # the confirmation is accepted by the fixture
    assert page.locator("#chat-inner article.turn:not(#pending-turn)").count() == 0
    assert not page.locator("#new-chat").is_visible()
    assert page.js_errors == []
