"""FR-UI-13: confirmations use the app's own dialog, not the browser's: the question, the action
named on its button, Cancel focused first; Cancel and Escape change nothing (stage 1)."""

import pytest

from tests.e2e.conftest import confirm
from tests.e2e.test_journey_a import SOP, ask, login, upload

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


def test_tc_ui_013_new_chat_asks_in_the_apps_own_dialog(page, server_url):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    ask(page, "What is the purpose of the inbound receiving procedure?")
    turns = page.locator("#chat-inner article.turn:not(#pending-turn)")
    dialog = page.locator("#confirm-dialog")

    page.click("#new-chat")
    dialog.wait_for()
    assert "Start a new chat?" in dialog.inner_text()
    assert page.evaluate("() => document.activeElement.value") == "cancel", "Cancel is focused first"
    page.click("#confirm-dialog [value=cancel]")
    assert not dialog.is_visible() and turns.count() == 1, "Cancel keeps the chat"

    page.click("#new-chat")
    dialog.wait_for()
    page.keyboard.press("Escape")
    assert not dialog.is_visible() and turns.count() == 1, "Escape keeps the chat"

    page.click("#new-chat")
    with page.expect_navigation():
        confirm(page, "Start a new chat")
    assert turns.count() == 0
    assert page.js_errors == [], "no browser dialog either"


def test_tc_ui_013_deleting_a_source_names_the_action(page, server_url):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    page.click(".source__delete")
    confirm(page, "Delete")
    page.wait_for_selector(".empty:has-text('No sources yet')")
    assert page.js_errors == []
