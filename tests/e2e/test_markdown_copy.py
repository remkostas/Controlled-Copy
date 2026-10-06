"""FR-OUT-01 in a real browser: copy a Resolution Card as Markdown (stage 3, fake model)."""

import pytest

from tests.e2e.test_journey_b import build_card, login

pytestmark = [pytest.mark.e2e, pytest.mark.stage3]


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"feature_governance": True})


def test_tc_ui_006_copy_a_card_as_markdown(page, server_url):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=server_url)
    login(page, server_url)
    page.select_option("#nb-select", label="Inbound Operations")
    page.wait_for_selector("h1:has-text('Inbound Operations')")
    card = build_card(page, page.locator("#scenario option").nth(1).inner_text())
    card.locator("[data-copy-markdown]").click()
    page.wait_for_selector("#toast:has-text('Copied as Markdown.')")
    copied = page.evaluate("navigator.clipboard.readText()")
    assert copied.startswith("# Resolution Card\n")
    assert "**Status: " in copied and "## Applicability" in copied
    download = card.locator("a:has-text('Download .md')")
    assert download.get_attribute("href").endswith(".md?download=true")
    assert page.js_errors == []
