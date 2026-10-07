"""Drive the real app (real model provider from .env) through Journey A and take screenshots.

Usage: python scripts/screenshot_app.py [output-dir]
Starts a temporary instance with its own data folder and access code; a few real model
calls are made (smoke check). Never used in tests.
"""

from __future__ import annotations

import secrets
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright
from pydantic import SecretStr

from controlled_copy.app import create_app
from controlled_copy.config import Settings

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "demo-data" / "inbound-operations"
DOCS = [
    "SOP-INB-001_inbound-receiving_rev3.md",
    "WI-QUA-004_damaged-material_rev2.md",
    "MATRIX-ESC-001_escalation-responsibilities_rev2.md",
]


def start(settings: Settings) -> tuple[uvicorn.Server, str]:
    app = create_app(settings, run_purge=False)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"


def ask(page, question: str) -> None:
    count = page.locator("#chat-inner article.turn:not(#pending-turn)").count()
    page.fill("#question", question)
    page.press("#question", "Enter")
    page.locator("#chat-inner article.turn:not(#pending-turn)").nth(count).wait_for(timeout=90_000)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    code = secrets.token_urlsafe(12)
    settings = Settings(_env_file=ROOT / ".env").model_copy(
        update={
            "app_access_code": SecretStr(code),
            "app_secret_key": SecretStr(secrets.token_urlsafe(40)),
            "data_dir": Path(tempfile.mkdtemp(prefix="cc-shots-")),
        }
    )
    server, base = start(settings)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.set_default_timeout(90_000)
            page.goto(base + "/")
            page.screenshot(path=str(out / "app-landing.png"))
            page.fill("#access-code", code)
            page.click("button[type=submit]")
            page.wait_for_url("**/app")
            page.click("button[data-toggle='new-notebook']")
            page.fill("#new-notebook-title", "Inbound receiving (demo)")
            page.click("#new-notebook button[type=submit]")
            page.wait_for_selector("h1:has-text('Inbound receiving (demo)')")
            page.screenshot(path=str(out / "app-empty-notebook.png"))
            for index, name in enumerate(DOCS, start=1):
                page.set_input_files("input[type=file]", str(CORPUS / name))
                page.locator(".source").nth(index - 1).wait_for()
            page.wait_for_selector(".suggestion", timeout=90_000)
            ask(page, "What is the quantity tolerance at goods receipt?")
            ask(page, "And who informs purchasing about it?")
            ask(page, "What is the forklift speed limit in the yard?")
            page.click(".studio-action:has-text('Briefing')")
            page.wait_for_selector("#studio-outputs details.output[open]", timeout=120_000)
            page.screenshot(path=str(out / "app-workspace.png"))
            page.locator("#chat-inner .answer button.cite").first.click()
            page.wait_for_selector("#viewer-slot mark#cited")
            page.wait_for_timeout(500)  # let the column-width transition finish
            page.evaluate("document.getElementById('cited').scrollIntoView({block: 'center'})")
            page.screenshot(path=str(out / "app-citation-viewer.png"))
            page.set_viewport_size({"width": 390, "height": 844})
            page.click("[data-close-viewer]")
            page.click(".mobile-tabs [data-tab='chat']")
            page.screenshot(path=str(out / "app-phone.png"))
            browser.close()
    finally:
        server.should_exit = True
    print(f"screenshots in {out}")


if __name__ == "__main__":
    main()
