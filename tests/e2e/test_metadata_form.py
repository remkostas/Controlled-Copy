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
