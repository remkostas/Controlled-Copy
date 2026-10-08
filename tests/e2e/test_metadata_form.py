"""FR-META-02 in a real browser: type document-control metadata for a pasted text (stage 3)."""

import pytest

from tests.e2e.test_journey_a import CONTRAST_JS
from tests.e2e.test_journey_b import login

pytestmark = [pytest.mark.e2e, pytest.mark.stage3]


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"feature_governance": True})


def test_tc_ui_007_typed_metadata_shows_on_the_source(page, server_url):
    login(page, server_url)
    page.click("summary:has-text('Document control')")
    page.fill("#doc-id", "DOCK-RULE-1")
    page.fill("#doc-revision", "2")
    page.select_option("#doc-status", "approved")
    page.fill("#doc-effective", "2026-01-01")
    page.fill("#doc-site", "all")
    assert page.evaluate(CONTRAST_JS) == []
    page.click("[data-toggle='paste-form']")
    page.fill("#paste-title", "Dock rule")
    page.fill("#paste-text", "Every damaged pallet is photographed before unloading.")
    page.click("#paste-form button[type=submit]")
    source = page.locator(".source:has-text('Dock rule')")
    source.wait_for()
    assert source.locator(".badge:has-text('DOCK-RULE-1')").count() == 1
    assert "asserted by uploader" in source.inner_text().lower()
    assert page.input_value("#doc-id") == "" and page.input_value("#doc-status") == "", "fields apply once"
    assert page.js_errors == []


FIELDS_FIT = """() => {
  const panel = document.querySelector('#sources-panel .panel__body').getBoundingClientRect();
  const boxes = [...document.querySelectorAll('#doc-control .input')].map((e) => e.getBoundingClientRect());
  const outside = boxes.filter((b) => b.left < panel.left - 1 || b.right > panel.right + 1).length;
  let overlaps = 0;
  boxes.forEach((a, i) => boxes.slice(i + 1).forEach((b) => {
    if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) overlaps += 1;
  }));
  return {outside, overlaps, count: boxes.length};
}"""


@pytest.mark.parametrize("width", [1366, 1100])
def test_tc_ui_007_the_form_fits_the_sources_panel(page, server_url, width):
    """Manual test round 1 (#7): the date field overflowed into the site field."""
    page.set_viewport_size({"width": width, "height": 768})
    login(page, server_url)
    page.click("summary:has-text('Document control')")
    page.wait_for_selector("#doc-effective", state="visible")
    result = page.evaluate(FIELDS_FIT)
    assert result["count"] == 6
    assert result["outside"] == 0, "every field stays inside the panel"
    assert result["overlaps"] == 0, "no field overlaps another"
