"""FR-STU-08: a new Studio output opens large over the chat, where it is seen at once; the
Studio list keeps it, and Open, Close, Escape and a citation behave (stage 1)."""

import pytest

from tests.e2e.test_journey_a import SOP, login, upload

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


def briefing(page, server_url):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    page.click(".studio-action:has-text('Briefing')")
    page.wait_for_selector("#studio-outputs details.output[open]")


def test_tc_stu_008_a_new_output_opens_large_over_the_chat(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    briefing(page, server_url)
    reader = page.locator("#output-reader")
    reader.wait_for()
    assert reader.locator("#reader-title").text_content() == "Briefing"
    assert reader.locator(".output__section").count() >= 1
    chat = page.locator(".panel--chat").bounding_box()
    box = reader.bounding_box()
    assert abs(box["width"] - chat["width"]) < 2 and abs(box["x"] - chat["x"]) < 2, "it covers the chat"
    assert page.locator("#studio-outputs details.output[open]").count() == 1, "Studio keeps it"
    page.click("[data-reader-close]")
    assert not reader.is_visible()
    page.click("#studio-outputs details.output[open] [data-read-output]")
    assert reader.is_visible()
    page.keyboard.press("Escape")
    assert not reader.is_visible()
    assert page.js_errors == []


def test_tc_stu_008_a_citation_in_the_reading_view_opens_its_passage(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    briefing(page, server_url)
    page.locator("#output-reader .cite").first.click()
    page.wait_for_selector("#viewer-slot mark#cited")
    assert not page.locator("#output-reader").is_visible(), "the chat is back next to the passage"
    assert page.js_errors == []


def test_tc_stu_008_no_automatic_reading_view_on_a_phone(page, server_url):
    page.set_viewport_size({"width": 390, "height": 844})
    login(page, server_url)
    page.click(".mobile-tabs [data-tab='sources']")
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    page.click(".mobile-tabs [data-tab='studio']")
    page.click(".studio-action:has-text('Briefing')")
    page.wait_for_selector("#studio-outputs details.output[open]")
    assert not page.locator("#output-reader").is_visible()
    assert page.js_errors == []
