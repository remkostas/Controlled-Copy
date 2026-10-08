"""Drive the real app (real model provider from .env) through Journey B and take screenshots.

Usage: python scripts/screenshot_governed.py [output-dir]
Starts a temporary instance with the governed layer on, its own data folder and access
code; three Resolution Cards make three real model calls (smoke check). Never used in tests.
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

CARDS = [
    ("Short delivery", "app-card-supported.png"),
    ("Damaged outer packaging", "app-card-conflict.png"),
    ("Storage location A-14", "app-card-expert.png"),
]


def build_card(page, scenario: str) -> None:
    outputs = page.locator("#studio-outputs details.output")
    before = outputs.count()
    page.select_option("#scenario", label=scenario)
    page.fill("#card-date", "2026-10-07")
    page.click(".card-form button[type=submit]")
    outputs.nth(before).wait_for(timeout=120_000)


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
        }
    )
    server, base = start(settings)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            page.set_default_timeout(90_000)
            page.goto(base + "/")
            page.fill("#access-code", code)
            page.click("button[type=submit]")
            page.wait_for_url("**/app")
            page.select_option("#nb-select", label="Inbound Operations")
            page.wait_for_selector("h1:has-text('Inbound Operations')")
            page.screenshot(path=str(out / "app-ops-workspace.png"))
            for scenario, name in CARDS:
                build_card(page, scenario)
                newest = page.locator("#studio-outputs details.output").first
                newest.scroll_into_view_if_needed()
                page.screenshot(path=str(out / name))
            # Evidence: open the first citation of the supported card in the viewer.
            if page.locator("#output-reader").is_visible():
                page.click("[data-reader-close]")
            supported = page.locator("#studio-outputs details.output").last
            supported.evaluate("el => { el.open = true; }")  # it may already be open
            supported.locator(".card-item button.cite").first.click()
            page.wait_for_selector("#viewer-slot mark#cited")
            page.wait_for_timeout(500)  # let the column-width transition finish
            page.evaluate("document.getElementById('cited').scrollIntoView({block: 'center'})")
            page.screenshot(path=str(out / "app-card-evidence.png"))
            browser.close()
    finally:
        server.should_exit = True
    print(f"screenshots in {out}")


if __name__ == "__main__":
    main()
