"""Drive the real app (real model provider from .env) through the Stage 3 features and take
screenshots: the model picker with a labelled answer, a Resolution Card with its export
buttons, and the document-control form.

Usage: python scripts/screenshot_stage3.py [output-dir]
Starts a temporary instance with both layers on, its own data folder and access code; one
answer and one card make real model calls (a few cents). Never used in tests.
"""

from __future__ import annotations

import secrets
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from pydantic import SecretStr
from screenshot_app import ROOT, start

from controlled_copy.config import Settings


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    code = secrets.token_urlsafe(12)
    settings = Settings(_env_file=ROOT / ".env").model_copy(
        update={
            "app_access_code": SecretStr(code),
            "app_secret_key": SecretStr(secrets.token_urlsafe(40)),
            "data_dir": Path(tempfile.mkdtemp(prefix="cc-shots-")),
            "feature_governance": True,
            "feature_model_picker": True,
        }
    )
    server, base = start(settings)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            page.set_default_timeout(120_000)
            page.goto(base + "/")
            page.fill("#access-code", code)
            page.click("button[type=submit]")
            page.wait_for_url("**/app")
            page.select_option("#nb-select", label="Inbound Operations")
            page.wait_for_selector("h1:has-text('Inbound Operations')")
            # Model picker: choose Gemini, ask, and show the labelled answer.
            page.select_option("#model-select", "google/gemini-3.5-flash-lite")
            page.wait_for_selector("#toast:has-text('Gemini 3.5 Flash Lite')")
            page.fill("#question", "What should operators do with excess units under error GR-204?")
            page.press("#question", "Enter")
            page.wait_for_selector("#chat-inner .answer__model")
            page.screenshot(path=str(out / "app-model-picker.png"))
            # A Resolution Card with GPT-6 Luna, scrolled to its export buttons.
            page.select_option("#model-select", "openai/gpt-6-luna")
            page.select_option("#scenario", label="Short delivery")
            page.fill("#card-date", "2026-10-07")
            page.click(".card-form button[type=submit]")
            card = page.locator("#studio-outputs details.output").first
            card.wait_for()
            card.locator(".output__actions").scroll_into_view_if_needed()
            page.screenshot(path=str(out / "app-card-export.png"))
            # The document-control form in a personal notebook.
            page.goto(base + "/app")
            page.select_option("#nb-select", index=1)
            page.wait_for_load_state()
            page.click("summary:has-text('Document control')")
            page.fill("#doc-id", "DOCK-RULE-1")
            page.fill("#doc-revision", "2")
            page.select_option("#doc-status", "approved")
            page.fill("#doc-site", "all")
            page.screenshot(path=str(out / "app-document-control-form.png"))
            browser.close()
    finally:
        server.should_exit = True
    print(f"screenshots in {out}")


if __name__ == "__main__":
    main()
