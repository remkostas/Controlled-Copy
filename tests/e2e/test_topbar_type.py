"""FR-UI-10: the top bar reads as one bar: its menus use the same type as its buttons, and the
demo button's label is one piece of text (stage 2, every layer on)."""

import pytest

from tests.e2e.test_journey_b import login

pytestmark = [pytest.mark.e2e, pytest.mark.stage2]


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"feature_governance": True, "feature_model_picker": True})


def type_of(page, selector: str) -> tuple[str, str, str]:
    return page.locator(selector).first.evaluate(
        "el => { const s = getComputedStyle(el); return [s.fontFamily, s.fontSize, s.fontWeight]; }"
    )


def test_tc_ui_010_menus_and_buttons_share_one_type(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    button = type_of(page, ".topbar__new")
    assert type_of(page, "#nb-select") == button, "notebook menu"
    assert type_of(page, ".model-select select") == button, "model menu"
    assert page.js_errors == []


def test_tc_ui_010_the_demo_label_has_no_gaps_inside(page, server_url):
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    demo = page.locator(".topbar a.btn", has_text="Inbound Operations")
    if not demo.count():  # the session opened in the demo itself; switch to the other notebook
        page.goto(
            server_url
            + "/app?nb="
            + page.locator("#nb-select option:not(:checked)").first.get_attribute("value")
        )
    # One icon and one label: the button's gap may only separate those two.
    assert demo.locator(":scope > span").count() == 1
    assert demo.inner_text().split() == ["Open", "the", "Inbound", "Operations", "demo"]
    assert page.js_errors == []
