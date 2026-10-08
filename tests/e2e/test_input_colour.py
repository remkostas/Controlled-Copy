"""NFR-UI-01 for typed text: an input in the dark top bar is still readable (stage 1)."""

import re

import pytest

from tests.e2e.test_journey_a import login

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]

COLOURS_JS = "el => { const s = getComputedStyle(el); return [s.color, s.backgroundColor]; }"


def contrast(foreground: str, background: str) -> float:
    """WCAG 2 contrast ratio of two opaque rgb() colours."""

    def luminance(colour: str) -> float:
        channels = [int(v) / 255 for v in re.findall(r"\d+", colour)[:3]]
        r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def test_tc_ui_003_typed_notebook_title_is_readable_in_the_top_bar(page, server_url):
    login(page, server_url)
    page.click("button[data-toggle='new-notebook']")
    page.fill("#new-notebook-title", "Receiving test")
    colour, background = page.locator("#new-notebook-title").evaluate(COLOURS_JS)
    assert contrast(colour, background) >= 4.5, f"text {colour} on {background} fails WCAG AA"
    assert colour == page.locator(".topbar").evaluate("() => getComputedStyle(document.body).color"), (
        "inputs use the body text colour"
    )
    assert page.js_errors == []
