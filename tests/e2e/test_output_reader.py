"""FR-STU-08: a new Studio output opens large over the chat, where it is seen at once; the
Studio list keeps it, marked while it is read, and Open, Close, Escape and a citation behave
(stage 1)."""

import pytest

from tests.e2e.test_journey_a import SOP, login, upload

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


def briefing(page, server_url):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    page.click(".studio-action:has-text('Briefing')")
    page.locator("#output-reader").wait_for()


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
    marked = page.locator("#studio-outputs details.output[aria-current='true']")
    assert marked.count() == 1, "Studio keeps it, marked as the one being read"
    assert page.locator("#studio-outputs details.output[open]").count() == 0, "closed while read"
    output = page.locator("#studio-outputs details.output").first
    background = "el => getComputedStyle(el).backgroundColor"
    page.wait_for_timeout(50)  # even reduced motion keeps a 1 ms colour transition
    while_read = output.evaluate(background)
    page.click("[data-reader-close]")
    assert not reader.is_visible()
    assert marked.count() == 0
    page.wait_for_timeout(50)
    assert output.evaluate(background) != while_read, "the marker is visible"
    assert page.locator("#studio-outputs details.output[open]").count() == 1, "back open in Studio"
    page.click("#studio-outputs details.output[open] [data-read-output]")
    assert reader.is_visible()
    page.keyboard.press("Escape")
    assert not reader.is_visible()
    assert page.js_errors == []


def test_tc_stu_008_a_citation_opens_its_passage_next_to_the_reading_view(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    briefing(page, server_url)
    reader = page.locator("#output-reader")
    sources = page.locator(".panel--sources").bounding_box()["width"]
    reader.locator(".cite").first.click()
    page.wait_for_selector("#viewer-slot mark#cited")
    assert reader.is_visible(), "the output stays open next to its passage"
    # Escape closes one thing at a time: the passage first, then the reading view.
    page.keyboard.press("Escape")
    assert page.locator("#viewer-slot [data-viewer]").count() == 0
    assert reader.is_visible()
    page.wait_for_timeout(300)
    assert page.locator(".panel--sources").bounding_box()["width"] == pytest.approx(sources, abs=2)
    page.keyboard.press("Escape")
    assert not reader.is_visible()
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
    # Opened by hand, closing goes back to the Studio tab with focus on Open (release audit).
    page.click("#studio-outputs details.output[open] [data-read-output]")
    page.locator("#output-reader").wait_for()
    page.click("[data-reader-close]")
    assert page.locator(".mobile-tabs [data-tab='studio']").get_attribute("aria-selected") == "true"
    assert page.evaluate("() => document.activeElement.matches('[data-read-output]')"), "back to Open"
    assert page.js_errors == []


def test_tc_stu_008_the_reading_view_keeps_and_returns_keyboard_focus(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    briefing(page, server_url)
    page.locator("#output-reader").wait_for()
    # What it covers cannot be reached while it is open.
    assert page.evaluate("() => document.querySelector('.panel--chat .chat').inert")
    assert page.evaluate("() => document.activeElement.closest('#output-reader') !== null")
    page.keyboard.press("Escape")
    assert not page.evaluate("() => document.querySelector('.panel--chat .chat').inert")
    focused = "() => { const el = document.activeElement; return el !== document.body && el.offsetParent !== null; }"
    assert page.evaluate(focused), "focus comes back to a visible control"
    page.click("#studio-outputs details.output[open] [data-read-output]")
    page.click("[data-reader-close]")
    assert page.evaluate("() => document.activeElement.matches('[data-read-output]')"), "back to Open"
    assert page.js_errors == []
