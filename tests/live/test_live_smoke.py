"""TC-LIVE-001 and TC-LIVE-002: checks against a running instance (deployed or local).

Manual, never in CI: `LIVE_URL=https://demo.example LIVE_ACCESS_CODE=... pytest -m smoke_live tests/live`.
TC-LIVE-001 makes no model calls. TC-LIVE-002 drives both journeys in a real browser with the
real model (a few cents); run it twice before recording. It uses its own session, so the
demo data of other visitors is untouched.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

import httpx
import pytest

pytestmark = [pytest.mark.smoke_live]

URL = os.environ.get("LIVE_URL", "").rstrip("/")
CODE = os.environ.get("LIVE_ACCESS_CODE", "")
MODEL_WAIT_MS = 150_000  # one model call can take 45 s, the fallback another 45 s

needs_live = pytest.mark.skipif(not URL or not CODE, reason="set LIVE_URL and LIVE_ACCESS_CODE")


@needs_live
def test_tc_live_001_health_landing_headers_and_certificate():
    with httpx.Client(timeout=20) as client:  # verifies the TLS certificate for https URLs
        assert client.get(URL + "/healthz").status_code == 200
        landing = client.get(URL + "/")
        assert landing.status_code == 200
        assert "Do not upload personal or confidential documents" in landing.text
        headers = landing.headers
        assert "default-src 'self'" in headers["content-security-policy"]
        assert "frame-ancestors 'none'" in headers["content-security-policy"]
        assert headers["x-content-type-options"] == "nosniff"
        assert "server" not in headers, "no server banner"
        refused = client.post(URL + "/access", data={"code": "not-the-code"}, headers={"Origin": URL})
        assert refused.status_code in (401, 429)
        if URL.startswith("https://"):
            assert "max-age=" in headers["strict-transport-security"]
            plain = client.get("http://" + urlsplit(URL).netloc + "/", follow_redirects=False)
            assert plain.status_code in (301, 302, 307, 308)
            assert plain.headers["location"].startswith("https://")


@pytest.fixture
def live_page():
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None
        browser = playwright.chromium.launch(executable_path=executable)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()
        page.set_default_timeout(MODEL_WAIT_MS)
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("dialog", lambda dialog: dialog.accept())
        page.js_errors = errors
        yield page
        browser.close()


def ask(page, question: str):
    before = page.locator("#chat-inner article.turn:not(#pending-turn)").count()
    page.fill("#question", question)
    page.press("#question", "Enter")
    turn = page.locator("#chat-inner article.turn:not(#pending-turn)").nth(before)
    turn.wait_for()
    return turn


@needs_live
def test_tc_live_002_both_journeys_with_the_real_model(live_page):
    page = live_page
    page.goto(URL + "/")
    page.fill("#access-code", CODE)
    page.click("button[type=submit]")
    page.wait_for_url("**/app")

    # Journey A: a pasted source, a cited answer, a refusal.
    page.click("[data-toggle='paste-form']")
    page.fill("#paste-title", "Live check note")
    page.fill(
        "#paste-text",
        "Live check note. Pallets that arrive wet must be dried for 24 hours before they are stored. "
        "The night shift checks the dock doors at 22:00.",
    )
    page.click("#paste-form button[type=submit]")
    page.locator(".source:has-text('Live check note')").wait_for()
    answer = ask(page, "How long must wet pallets be dried?")
    assert answer.locator("button.cite").count() >= 1, answer.inner_text()
    assert "24 hours" in answer.inner_text()
    refusal = ask(page, "What is the speed limit for forklifts in the yard?")
    assert "Not in the selected sources" in refusal.inner_text()

    # Model picker (when switched on): the next answer names the chosen model.
    if page.locator("#model-select").count():
        page.select_option("#model-select", "google/gemini-3.5-flash-lite")
        page.wait_for_selector("#toast:has-text('Gemini 3.5 Flash Lite')")
        turn = ask(page, "When are the dock doors checked?")
        assert "gemini-3.5-flash-lite" in turn.locator(".answer__model").inner_text()
        page.select_option("#model-select", "openai/gpt-6-luna")
        page.wait_for_selector("#toast:has-text('GPT-6 Luna')")

    # Journey B (when the governed layer is on): a Resolution Card on the curated workspace.
    options = page.locator("#nb-select option", has_text="Inbound Operations")
    if options.count():
        page.select_option("#nb-select", label="Inbound Operations")
        page.wait_for_selector("h1:has-text('Inbound Operations')")
        assert page.locator(".source").count() == 8
        outputs = page.locator("#studio-outputs details.output")
        before = outputs.count()
        page.select_option("#scenario", label="Short delivery")
        page.click(".card-form button[type=submit]")
        outputs.nth(before).wait_for()
        card = outputs.first
        status = card.locator(".card-status").inner_text()
        assert status in {
            "Supported by an approved instruction",
            "Context incomplete",
            "Expert confirmation required",
        }, status
        assert "SOP-INB-001 rev 2" in card.inner_text(), "the obsolete revision is named as not applied"
        url = card.locator("[data-copy-markdown]").get_attribute("data-copy-markdown")
        markdown = page.evaluate("url => fetch(url).then(r => r.text())", url)
        assert markdown.startswith("# Resolution Card")
        assert re.search(r"\[1\] .+: \".+\"", markdown), "the export lists verified quotes"
    assert page.js_errors == []
