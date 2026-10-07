"""NFR-UI-01 for typed text: an input in the dark top bar is still readable (stage 1)."""

import pytest

from tests.e2e.test_journey_a import login

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]

COLOURS_JS = "el => { const s = getComputedStyle(el); return [s.color, s.backgroundColor]; }"


def test_tc_ui_003_typed_notebook_title_is_readable_in_the_top_bar(page, server_url):
    login(page, server_url)
    page.click("button[data-toggle='new-notebook']")
    page.fill("#new-notebook-title", "Receiving test")
    colour, background = page.locator("#new-notebook-title").evaluate(COLOURS_JS)
    assert colour != background, f"text {colour} on {background}"
    assert colour == page.locator(".topbar").evaluate("() => getComputedStyle(document.body).color"), (
        "inputs use the body text colour"
    )
    assert page.js_errors == []
