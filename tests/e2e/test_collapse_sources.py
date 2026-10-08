"""FR-UI-12: the Sources and Studio panels can be collapsed for more room, as in NotebookLM
(stage 1)."""

import pytest

from tests.e2e.test_journey_a import login
from tests.e2e.test_layout import cite_target, long_source  # noqa: F401  (fixture)

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


def width(page, selector: str) -> float:
    return page.locator(selector).evaluate("el => el.getBoundingClientRect().width")


def toggle(page):
    return page.locator("[data-collapse='sources']")


def test_tc_ui_012_collapse_gives_the_chat_room_and_is_kept(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    chat = width(page, ".panel--chat")
    toggle(page).click()
    page.wait_for_function(
        "() => document.querySelector('.panel--sources').getBoundingClientRect().width < 60"
    )
    assert width(page, ".panel--chat") > chat + 200
    assert toggle(page).get_attribute("aria-expanded") == "false"
    assert toggle(page).get_attribute("aria-label") == "Show sources"
    assert not page.locator("#source-browser").is_visible()
    page.reload()
    assert width(page, ".panel--sources") < 60, "kept after reload"
    toggle(page).click()
    page.wait_for_function(
        "() => document.querySelector('.panel--sources').getBoundingClientRect().width > 200"
    )
    assert toggle(page).get_attribute("aria-expanded") == "true"
    assert page.js_errors == []


def test_tc_ui_012_a_citation_opens_the_collapsed_panel(page, server_url, long_source):  # noqa: F811
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    toggle(page).click()
    page.wait_for_function(
        "() => document.querySelector('.panel--sources').getBoundingClientRect().width < 60"
    )
    cite_target(page, long_source)
    assert page.locator(".workspace.is-reading:not(.sources-collapsed)").count() == 1
    assert page.locator("#cited").is_visible()
    assert page.js_errors == []


def test_tc_ui_012_no_collapse_in_the_tab_layout(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    toggle(page).click()
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function(
        "() => !document.querySelector('.workspace').classList.contains('sources-collapsed')"
    )
    assert not toggle(page).is_visible()
    assert page.js_errors == []


def test_tc_ui_012_expanding_after_widening_studio_leaves_the_chat_room(page, server_url):
    from tests.e2e.test_resize_panels import CHAT_MIN, drag

    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    toggle(page).click()
    page.wait_for_function(
        "() => document.querySelector('.panel--sources').getBoundingClientRect().width < 60"
    )
    drag(page, "[data-resize='studio']", -900)  # as wide as the collapsed Sources allow
    toggle(page).click()
    page.wait_for_function(
        "() => document.querySelector('.panel--sources').getBoundingClientRect().width > 200"
    )
    assert width(page, ".panel--chat") >= CHAT_MIN - 2, width(page, ".panel--chat")
    # Release audit: resetting the Sources width by double-click must re-fit too.
    page.dblclick("[data-resize='sources']")
    page.wait_for_timeout(100)
    assert width(page, ".panel--chat") >= CHAT_MIN - 2, width(page, ".panel--chat")
    assert page.js_errors == []


def test_tc_ui_012_studio_collapses_too_and_is_kept(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    chat = width(page, ".panel--chat")
    studio = page.locator("[data-collapse='studio']")
    assert studio.get_attribute("aria-label") == "Hide Studio"
    # Both toggles sit on the inner edge, next to the chat, at the same distance from it.
    s_box, s_panel = toggle(page).bounding_box(), page.locator(".panel--sources").bounding_box()
    t_box, t_panel = studio.bounding_box(), page.locator(".panel--studio").bounding_box()
    assert t_box["x"] < page.locator("#studio-title").bounding_box()["x"], "before the word Studio"
    inner_sources = s_panel["x"] + s_panel["width"] - (s_box["x"] + s_box["width"])
    assert t_box["x"] - t_panel["x"] == pytest.approx(inner_sources, abs=1)
    studio.click()
    page.wait_for_function(
        "() => document.querySelector('.panel--studio').getBoundingClientRect().width < 60"
    )
    assert width(page, ".panel--chat") > chat + 200, "the chat gains the room"
    assert studio.get_attribute("aria-label") == "Show Studio"
    assert not page.locator(".studio-actions").is_visible()
    page.reload()
    assert width(page, ".panel--studio") < 60, "kept after a reload"
    toggle(page).click()  # both collapsed: the chat takes the window
    page.wait_for_function(
        "() => document.querySelector('.panel--sources').getBoundingClientRect().width < 60"
    )
    assert width(page, ".panel--chat") > 1366 - 2 * 60 - 4
    page.locator("[data-collapse='studio']").click()
    page.wait_for_function(
        "() => document.querySelector('.panel--studio').getBoundingClientRect().width > 200"
    )
    assert page.locator(".studio-actions").is_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    page.click(".mobile-tabs [data-tab='studio']")
    assert not page.locator("[data-collapse='studio']").is_visible(), "no collapse in the tab layout"
    assert page.js_errors == []
