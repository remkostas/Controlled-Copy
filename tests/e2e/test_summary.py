"""FR-STU-07 in a real browser: the chat's Summary button writes a cited Summary in Studio,
and on a phone the Studio tab opens to show it (stage 1)."""

import pytest

from tests.e2e.test_journey_a import SOP, login, upload

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


@pytest.mark.parametrize(("width", "height"), [(1366, 768), (390, 844)])
def test_tc_stu_007_summary_from_the_chat(page, server_url, width, height):
    page.set_viewport_size({"width": width, "height": height})
    login(page, server_url)
    if width < 900:
        page.click(".mobile-tabs [data-tab='sources']")
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')", state="attached")
    if width < 900:
        page.click(".mobile-tabs [data-tab='chat']")
    page.click("[data-chat-summary]")
    output = page.locator("#studio-outputs details.output").first
    output.wait_for(state="attached")
    assert "Summary" in output.locator(".output__name").inner_text()
    # A wide screen shows it large over the chat; a phone in the Studio tab.
    shown = page.locator("#output-reader") if width > 900 else output
    headings = [h.lower() for h in shown.locator(".output__section h3").all_inner_texts()]
    assert headings == ["in short", "main topics"]
    assert shown.is_visible(), "the new Summary is on screen"
    assert page.js_errors == []
