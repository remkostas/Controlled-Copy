"""FR-OUT-02 in a real browser: Print opens the stamped page and the print dialog (stage 1)."""

import pytest

from tests.e2e.test_journey_a import CONTRAST_JS, SOP, login, upload

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


def test_tc_out_002_print_opens_a_stamped_page(page, server_url):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    page.click(".studio-action:has-text('Briefing')")
    page.wait_for_selector("#studio-outputs details.output[open]")
    with page.context.expect_page() as opened:
        page.click("#studio-outputs details.output[open] a:has-text('Print')")
    sheet = opened.value
    sheet.add_init_script("window.__printed = 0; window.print = () => { window.__printed += 1; };")
    sheet.reload()
    sheet.wait_for_selector(".print-stamp")
    sheet.wait_for_timeout(600)  # the page prints 300 ms after it loads
    assert sheet.evaluate("() => window.__printed") == 1, "printed once on open"
    sheet.click("[data-print]")
    assert sheet.evaluate("() => window.__printed") == 2
    assert sheet.evaluate(CONTRAST_JS) == []
