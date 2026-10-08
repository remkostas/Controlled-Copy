"""FR-UI-11: a request that cannot reach the server says so, and a typed question is kept
(stage 1)."""

import pytest

from tests.e2e.test_journey_a import login

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


def test_tc_ui_011_a_lost_connection_is_reported_and_the_question_kept(page, server_url):
    login(page, server_url)
    page.click("[data-toggle='paste-form']")
    page.fill("#paste-title", "Note")
    page.fill("#paste-text", "Pallets that arrive wet must be dried for 24 hours before they are stored.")
    page.click("#paste-form button[type=submit]")
    page.locator(".source:has-text('Note')").wait_for()
    page.context.set_offline(True)
    page.fill("#question", "How long must wet pallets be dried?")
    page.press("#question", "Enter")
    page.locator("#toast", has_text="The connection was interrupted").wait_for()
    assert page.input_value("#question") == "How long must wet pallets be dried?"
    page.context.set_offline(False)
    page.press("#question", "Enter")
    page.locator("#chat-inner article.turn:not(#pending-turn)").first.wait_for()
    # The page reported the failed request itself; nothing else went wrong.
    assert all(
        "ERR_INTERNET_DISCONNECTED" in e or "sendError" in e or "afterRequest" in e for e in page.js_errors
    )
