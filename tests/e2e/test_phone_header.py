"""FR-UI-09: on a phone the header stays two short rows, and its short labels keep their full
accessible names (stage 2, every layer on)."""

import pytest

from tests.e2e.test_journey_b import login

pytestmark = [pytest.mark.e2e, pytest.mark.stage2]


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"feature_governance": True, "feature_model_picker": True})


@pytest.mark.parametrize("phone_width", [320, 360, 375, 390])
def test_tc_ui_009_the_phone_header_leaves_the_panels_the_screen(page, server_url, phone_width):
    page.set_viewport_size({"width": phone_width, "height": 844})
    login(page, server_url)
    header = page.locator(".topbar").bounding_box()["height"]
    assert header <= 100, f"the header is {header} px high at {phone_width} px (it was 189)"
    menu = page.locator("#nb-select").bounding_box()["width"]
    assert page.get_by_role("button", name="Log out").is_visible()
    assert page.get_by_role("button", name="New notebook").is_visible()
    assert page.get_by_role("link", name="Open the Inbound Operations demo").is_visible()
    assert page.locator("#model-select").is_visible()
    # In the demo notebook the button says Reset instead; that row must fit too.
    page.select_option("#nb-select", label="Inbound Operations")
    page.wait_for_selector("h1:has-text('Inbound Operations')", state="attached")
    header = page.locator(".topbar").bounding_box()["height"]
    assert header <= 100, f"the demo notebook's header is {header} px high at {phone_width} px"
    # Round 2: the notebook menu keeps its width when switching notebooks.
    assert page.locator("#nb-select").bounding_box()["width"] == pytest.approx(menu, abs=2)
    page.set_viewport_size({"width": 1366, "height": 768})
    assert "New notebook" in page.locator(".topbar__new").inner_text(), "the desktop keeps full labels"
    assert page.js_errors == []
