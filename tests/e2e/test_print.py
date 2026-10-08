"""FR-OUT-02 in a real browser: Print opens the print dialog from the workspace, through the
stamped page in a hidden frame, without leaving the notebook (stage 1)."""

import pytest

from tests.e2e.test_journey_a import CONTRAST_JS, SOP, login, upload

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]

COUNT_PRINTS = "window.__printed = 0; window.print = () => { window.__printed += 1; };"


def briefing(page, server_url):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    page.click(".studio-action:has-text('Briefing')")
    page.wait_for_selector("#studio-outputs details.output[open]")
    return page.locator("#studio-outputs details.output[open] a:has-text('Print')")


def test_tc_out_002_print_opens_the_dialog_in_place(page, server_url):
    page.context.add_init_script(COUNT_PRINTS)  # every frame, including the print frame
    link = briefing(page, server_url)
    assert 'd="M6 9V3' in link.inner_html(), "a printer icon, not a copy icon"
    pages_before = len(page.context.pages)
    url_before = page.url
    link.click()
    frame_element = page.wait_for_selector("#print-frame", state="attached")
    frame = frame_element.content_frame()
    frame.wait_for_selector(".print-stamp")
    frame.wait_for_timeout(600)  # the page prints 300 ms after it loads
    assert frame.evaluate("() => window.__printed") == 1, "printed once"
    assert len(page.context.pages) == pages_before, "no new tab"
    assert page.url == url_before, "the notebook stays open"
    assert page.js_errors == []


def test_tc_out_002_the_stamped_page_prints_again_from_its_button(page, server_url):
    link = briefing(page, server_url)
    sheet = page.context.new_page()
    sheet.add_init_script(COUNT_PRINTS)
    sheet.goto(server_url + link.get_attribute("href"))
    sheet.wait_for_selector(".print-stamp")
    sheet.wait_for_timeout(600)
    assert sheet.evaluate("() => window.__printed") == 1, "printed once on open"
    sheet.click("[data-print]")
    assert sheet.evaluate("() => window.__printed") == 2
    assert sheet.evaluate(CONTRAST_JS) == []
