"""FR-UI-08: the side panels can be resized and the chat always keeps room (stage 1)."""

import pytest

from tests.e2e.test_journey_a import login
from tests.e2e.test_layout import cite_target, long_source  # noqa: F401  (fixture)

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]

CHAT_MIN = 352


def width(page, selector: str) -> float:
    return page.locator(selector).evaluate("el => el.getBoundingClientRect().width")


def drag(page, handle: str, dx: int):
    box = page.locator(handle).bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx / 2, y)
    page.mouse.move(x + dx, y)
    page.mouse.up()


def test_tc_ui_008_drag_widens_sources_and_the_width_is_kept(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    before = width(page, ".panel--sources")
    drag(page, "[data-resize='sources']", 120)
    assert width(page, ".panel--sources") == pytest.approx(before + 120, abs=4)
    page.reload()
    assert width(page, ".panel--sources") == pytest.approx(before + 120, abs=4), "kept after reload"
    page.dblclick("[data-resize='sources']")
    page.wait_for_timeout(400)  # the reset animates back
    assert width(page, ".panel--sources") == pytest.approx(before, abs=4), "double-click resets"
    assert page.js_errors == []


def test_tc_ui_008_dragging_too_far_leaves_the_chat_its_minimum(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    drag(page, "[data-resize='studio']", -900)
    drag(page, "[data-resize='sources']", 900)
    assert width(page, ".panel--chat") >= CHAT_MIN - 2
    assert page.js_errors == []


def test_tc_ui_008_arrow_keys_resize_the_studio_panel(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    before = width(page, ".panel--studio")
    page.focus("[data-resize='studio']")
    for _ in range(2):  # quick presses: each step counts from the last set width
        page.keyboard.press("ArrowLeft")
    assert width(page, ".panel--studio") == pytest.approx(before + 48, abs=4)
    handle = page.locator("[data-resize='studio']")
    assert handle.get_attribute("role") == "separator"
    assert int(handle.get_attribute("aria-valuenow")) == pytest.approx(before + 48, abs=4)
    assert page.js_errors == []


def test_tc_ui_008_a_key_step_applies_at_once_without_animating(page, server_url):
    """The new width must be computed while the animation is off. Otherwise the step starts a
    transition, and a read in the next frame still sees the old width (a flaky CI failure)."""
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    before, after = page.evaluate(
        """async () => {
            const handle = document.querySelector("[data-resize='studio']");
            const panel = document.querySelector(".panel--studio");
            const before = panel.getBoundingClientRect().width;
            handle.focus();
            handle.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft", bubbles: true }));
            await new Promise((resolve) => requestAnimationFrame(resolve));
            return [before, panel.getBoundingClientRect().width];
        }"""
    )
    assert after == pytest.approx(before + 24, abs=2)
    assert page.js_errors == []


@pytest.mark.parametrize("viewport_width", [1000, 1366])
def test_tc_ui_008_reading_a_source_leaves_the_chat_room(page, server_url, long_source, viewport_width):  # noqa: F811
    page.set_viewport_size({"width": viewport_width, "height": 768})
    login(page, server_url)
    cite_target(page, long_source)
    assert width(page, ".panel--chat") >= CHAT_MIN - 2
    assert page.js_errors == []


def test_tc_ui_008_no_handles_in_the_tab_layout(page, server_url):
    page.set_viewport_size({"width": 390, "height": 844})
    login(page, server_url)
    assert page.locator("[data-resize]:visible").count() == 0
    assert page.js_errors == []
