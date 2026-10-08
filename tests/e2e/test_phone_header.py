"""FR-UI-09: on a phone the header stays two short rows, and its short labels keep their full
accessible names (stage 2, every layer on)."""

import pytest

from tests.e2e.test_journey_b import login

pytestmark = [pytest.mark.e2e, pytest.mark.stage2]


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"feature_governance": True, "feature_model_picker": True})


def test_tc_ui_009_the_phone_header_leaves_the_panels_the_screen(page, server_url):
    page.set_viewport_size({"width": 390, "height": 844})
    login(page, server_url)
    header = page.locator(".topbar").bounding_box()["height"]
    assert header <= 100, f"the header is {header} px high on a phone (it was 189)"
    assert page.get_by_role("button", name="New notebook").is_visible()
    assert page.get_by_role("link", name="Open the Inbound Operations demo").is_visible()
    assert page.locator("#model-select").is_visible()
    page.set_viewport_size({"width": 1366, "height": 768})
    assert "New notebook" in page.locator(".topbar__new").inner_text(), "the desktop keeps full labels"
    assert page.js_errors == []
