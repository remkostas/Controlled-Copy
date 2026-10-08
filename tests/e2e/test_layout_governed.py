"""FR-UI-01 in the governed workspace: a Resolution Card and its citations never scroll the
locked page (stage 2, fake model). The card's tables carry visually hidden captions, which are
absolutely positioned; outside a positioned scroll box they gave the page extra height."""

import pytest

from tests.e2e.test_journey_b import build_card, login

pytestmark = [pytest.mark.e2e, pytest.mark.stage2]

PAGE = "() => ({doc: document.documentElement.scrollHeight, win: innerHeight, y: scrollY})"


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"feature_governance": True})


@pytest.mark.parametrize(("width", "height"), [(1366, 768), (390, 844)])
def test_tc_ui_001_a_card_and_its_citation_leave_the_page_in_place(page, server_url, width, height):
    page.set_viewport_size({"width": width, "height": height})
    login(page, server_url)
    page.select_option("#nb-select", label="Inbound Operations")
    page.wait_for_selector("h1:has-text('Inbound Operations')")
    if width < 900:
        page.click(".mobile-tabs [data-tab='studio']")
    card = build_card(page, "Short delivery")
    state = page.evaluate(PAGE)
    assert state["y"] == 0 and state["doc"] == state["win"], f"after the card: {state}"
    card.locator(".card-item button.cite").first.click()
    page.wait_for_selector("#viewer-slot mark#cited", state="attached")
    page.wait_for_timeout(500)
    state = page.evaluate(PAGE)
    assert state["y"] == 0 and state["doc"] == state["win"], f"after a card citation: {state}"
    if width < 900:
        assert page.locator(".mobile-tabs").bounding_box()["y"] >= 0, "the tabs stay on screen"
    assert page.js_errors == []


def test_tc_ui_001_a_situation_without_spaces_does_not_widen_studio(page, server_url):
    """Release audit: 2,000 characters without a space widened the Studio card to about 15,000 px."""
    page.set_viewport_size({"width": 1366, "height": 768})
    login(page, server_url)
    page.select_option("#nb-select", label="Inbound Operations")
    page.wait_for_selector("h1:has-text('Inbound Operations')")
    outputs = page.locator("#studio-outputs details.output")
    before = outputs.count()
    page.fill("#situation", "x" * 2000)
    page.click(".card-form button[type=submit]")
    outputs.nth(before).wait_for(state="attached")
    page.locator("#output-reader").wait_for()
    sideways = "el => el.scrollWidth - el.clientWidth"
    assert page.locator("#output-reader .reader__body").evaluate(sideways) <= 1
    page.click("[data-reader-close]")
    assert page.locator(".panel--studio .panel__body").evaluate(sideways) <= 1
    assert page.js_errors == []
