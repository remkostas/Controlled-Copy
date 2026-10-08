"""FR-UI-10: the top bar reads as one bar: its menus use the same type as its buttons, the
demo button's label is one piece of text, and nothing overlaps in a narrow or zoomed-in desktop
window (stage 2, every layer on)."""

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


OVERLAPS = """() => {
  const items = Array.from(document.querySelectorAll('.topbar select, .topbar .btn, .topbar .brand'))
    .filter((el) => el.offsetParent !== null && !el.closest('[hidden]'));
  const hits = [];
  items.forEach((a, i) => {
    const r = a.getBoundingClientRect();
    if (r.right > innerWidth + 0.5) hits.push(`${a.className || a.id} past the edge`);
    items.slice(i + 1).forEach((b) => {
      const s = b.getBoundingClientRect();
      if (r.left < s.right - 0.5 && s.left < r.right - 0.5 && r.top < s.bottom - 0.5 && s.top < r.bottom - 0.5)
        hits.push(`${a.className || a.id} overlaps ${b.className || b.id}`);
    });
  });
  return hits;
}"""


@pytest.mark.parametrize("width", [1920, 1280, 1190, 1100, 1000, 901])
def test_tc_ui_010_nothing_overlaps_in_a_narrow_or_zoomed_in_window(page, server_url, width):
    """Round 2: at 160 to 210 % zoom (about 900 to 1200 px) the menus slid under the buttons."""
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    for notebook in ("Untitled notebook", "Inbound Operations"):
        page.set_viewport_size({"width": 1366, "height": 768})
        if page.eval_on_selector("#nb-select", "s => s.selectedOptions[0].text") != notebook:
            page.select_option("#nb-select", label=notebook)
            page.wait_for_selector(f"h1:has-text('{notebook}')")
        page.set_viewport_size({"width": width, "height": 768})
        assert page.evaluate(OVERLAPS) == [], f"{notebook} at {width} px"
        assert page.get_by_role("button", name="Log out").is_visible()
    assert page.js_errors == []
