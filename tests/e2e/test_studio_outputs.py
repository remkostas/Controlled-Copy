"""FR-STU-06 in a real browser: a new output is the one that is open and in view (stage 1)."""

import pytest

from tests.e2e.test_journey_a import SOP, login, upload

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]

IN_VIEW_JS = """el => {
  const box = el.getBoundingClientRect();
  const pane = el.closest('.panel__body').getBoundingClientRect();
  return box.top >= pane.top - 1 && box.top < pane.bottom;
}"""
TO_BOTTOM_JS = "el => { el.scrollTop = el.scrollHeight; }"


def test_tc_stu_006_only_the_newest_output_stays_open(page, server_url):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    outputs = page.locator("#studio-outputs details.output")
    studio = page.locator(".panel--studio .panel__body")
    for count in (1, 2, 3):
        # Read the older outputs first: the panel is scrolled down when the new one arrives.
        studio.evaluate(TO_BOTTOM_JS)
        page.click(".studio-action:has-text('Briefing')")
        outputs.nth(count - 1).wait_for(state="attached")
    assert [outputs.nth(i).evaluate("el => el.open") for i in range(3)] == [True, False, False]
    assert outputs.first.evaluate(IN_VIEW_JS)
    assert page.evaluate("() => scrollY") == 0, "only the Studio panel scrolls, never the page"
    assert page.js_errors == []
