"""FR-UI-03: Journey B (governed workspace) in a real browser (stage 2, fake model)."""

import pytest

from tests.conftest import ACCESS_CODE

pytestmark = [pytest.mark.e2e, pytest.mark.stage2]


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"feature_governance": True})


def login(page, server_url):
    page.goto(server_url + "/")
    page.fill("#access-code", ACCESS_CODE)
    page.click("button[type=submit]")
    page.wait_for_url("**/app")


def build_card(page, scenario: str):
    """Pick a scenario, fix the date, build the card; returns the new output."""
    outputs = page.locator("#studio-outputs details.output")
    before = outputs.count()
    page.select_option("#scenario", label=scenario)
    assert page.input_value("#situation"), "choosing a scenario fills the situation"
    page.fill("#card-date", "2026-10-07")
    page.click(".card-form button[type=submit]")
    outputs.nth(before).wait_for()
    return outputs.first


def test_tc_ui_004_journey_b_end_to_end(page, server_url):
    login(page, server_url)
    # The visitor's own Inbound Operations workspace, seeded with the curated documents.
    page.select_option("#nb-select", label="Inbound Operations")
    page.wait_for_selector("h1:has-text('Inbound Operations')")
    assert page.locator(".source").count() == 8
    assert page.locator(".source .badge:has-text('SOP-INB-001')").count() == 2

    # Scenario 1: supported by an approved, current instruction.
    card = build_card(page, "Short delivery")
    assert card.locator(".card-status").inner_text() == "Supported by an approved instruction"
    assert card.locator("table.applicability td:has-text('SOP-INB-001 rev 2')").count() == 1, (
        "listed as not applied"
    )

    # Open the evidence behind an item: the viewer shows the highlighted passage.
    card.locator(".card-item button.cite").first.click()
    page.wait_for_selector("#viewer-slot mark#cited")
    assert page.locator(".titleblock").is_visible()
    page.click("[data-close-viewer]")
    page.wait_for_selector("#source-browser", state="visible")

    # Scenario 5: the obsolete revision is named in a warning, never used.
    card = build_card(page, "Which revision applies?")
    warning = card.locator(".card-warning", has_text="SOP-INB-001 rev 2")
    assert warning.count() == 1 and "obsolete" in warning.inner_text()
    used = card.locator("table.applicability").first.inner_text()
    assert "SOP-INB-001 rev 2" not in used

    # Scenario 6: A-14 is only covered by another site's instruction.
    card = build_card(page, "Storage location A-14")
    assert card.locator(".card-status").inner_text() == "Expert confirmation required"
    assert card.locator(".badge--warn:has-text('A-14')").count() == 1
    assert "other site (HAM-02)" in card.locator("table.applicability").last.inner_text()

    # Reset restores the original documents and removes the cards.
    before = page.url
    page.click("button:has-text('Reset the Inbound Operations demo')")
    page.wait_for_url(lambda url: url != before)  # a fresh copy has a new notebook ID
    page.wait_for_selector("h1:has-text('Inbound Operations')")
    assert page.locator("#studio-outputs details.output").count() == 0
    assert page.locator(".source").count() == 8
    assert page.js_errors == []


def test_req_01_a_refused_card_renders_and_survives_a_reload(page, server_url):
    """Full audit REQ-01: an off-topic situation gives a refusal card, and the workspace
    still loads afterwards."""
    login(page, server_url)
    page.select_option("#nb-select", label="Inbound Operations")
    page.wait_for_selector("h1:has-text('Inbound Operations')")
    outputs = page.locator("#studio-outputs details.output")
    before = outputs.count()
    page.fill("#situation", "What is the forklift speed limit in the yard?")
    page.click(".card-form button[type=submit]")
    outputs.nth(before).wait_for()
    assert "Not in the selected sources" in outputs.first.inner_text()
    page.reload()
    page.wait_for_selector("h1:has-text('Inbound Operations')")
    assert "Not in the selected sources" in page.locator("#studio-outputs").inner_text()
    assert page.js_errors == []
