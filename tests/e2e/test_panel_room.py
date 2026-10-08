"""FR-UI-08: the chat keeps its minimum width when a source opens or closes after the side
panels were resized, and after a restored or narrowed layout (stage 1)."""

import json

import pytest

from tests.e2e.test_journey_a import login
from tests.e2e.test_layout import cite_target, long_source  # noqa: F401  (fixture)
from tests.e2e.test_resize_panels import CHAT_MIN, drag, width

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


def chat_has_room(page) -> bool:
    return width(page, ".panel--chat") >= CHAT_MIN - 2


def test_tc_ui_008_a_wide_studio_still_leaves_the_chat_room_while_reading(page, server_url, long_source):  # noqa: F811
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    drag(page, "[data-resize='studio']", -900)  # as wide as it may get
    assert chat_has_room(page)
    cite_target(page, long_source)
    assert chat_has_room(page), width(page, ".panel--chat")
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    assert chat_has_room(page)
    assert page.js_errors == []


def test_tc_ui_008_closing_a_source_in_a_narrower_window_leaves_the_chat_room(page, server_url, long_source):  # noqa: F811
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    drag(page, "[data-resize='sources']", 900)
    cite_target(page, long_source)
    page.set_viewport_size({"width": 1000, "height": 768})
    page.wait_for_timeout(300)  # the resize handler is debounced
    assert chat_has_room(page), width(page, ".panel--chat")
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    assert chat_has_room(page), width(page, ".panel--chat")
    assert page.js_errors == []


def test_tc_ui_008_a_restored_wide_reader_leaves_the_chat_room(page, server_url, long_source):  # noqa: F811
    page.set_viewport_size({"width": 1000, "height": 768})
    login(page, server_url)
    page.evaluate(
        "w => localStorage.setItem('cc-panel-widths', w)",
        json.dumps({"--col-reader": 675, "--col-studio": 400}),
    )
    page.reload()
    cite_target(page, long_source)
    assert chat_has_room(page), width(page, ".panel--chat")
    assert page.js_errors == []
