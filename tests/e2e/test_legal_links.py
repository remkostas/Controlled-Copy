"""FR-LEG-02 in a real browser: in the workspace, Privacy and Impressum stay on screen in every
layout and panel state, next to the AI note (stage 1)."""

import pytest

from tests.e2e.test_journey_a import login
from tests.e2e.test_layout import cite_target, long_source  # noqa: F401  (fixture)

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"impressum_url": "https://example.com/impressum"})


def links_on_screen(page) -> bool:
    for name in ("Privacy", "Impressum"):
        link = page.locator(".appfoot").get_by_role("link", name=name)
        box = link.bounding_box()
        size = page.viewport_size
        if not link.is_visible() or box is None or box["y"] + box["height"] > size["height"] + 1:
            return False
    return page.locator(".appfoot__note").is_visible()


def test_tc_leg_002_the_links_stay_on_screen_in_the_workspace(page, server_url, long_source):  # noqa: F811
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    assert links_on_screen(page)
    cite_target(page, long_source)  # a long source, open in the Sources panel
    assert links_on_screen(page)
    page.keyboard.press("Escape")
    page.click("[data-collapse='sources']")
    assert links_on_screen(page), "with Sources collapsed"
    page.set_viewport_size({"width": 390, "height": 844})
    for tab in ("sources", "chat", "studio"):
        page.click(f".mobile-tabs [data-tab='{tab}']")
        assert links_on_screen(page), f"on a phone, {tab} tab"
    assert page.js_errors == []
