"""Screenshot the rendered mock-up pages (desktop and phone) with Playwright.

Usage: python scripts/screenshot_mockup.py [output-dir]
Serves the repository root on 127.0.0.1 so fonts load over HTTP, not file://.
"""

from __future__ import annotations

import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

PAGES = [
    ("landing", "docs/mockup/landing.html", (1366, 768)),
    ("workspace", "docs/mockup/workspace.html", (1366, 768)),
    ("workspace-viewer", "docs/mockup/workspace-viewer.html", (1366, 768)),
    ("workspace-empty", "docs/mockup/workspace-empty.html", (1366, 768)),
    ("workspace-phone", "docs/mockup/workspace.html", (390, 844)),
]


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for name, path, (width, height) in PAGES:
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page.goto(base + path)
                page.wait_for_load_state("networkidle")
                page.evaluate("document.fonts.ready")
                if name == "workspace-viewer":
                    page.evaluate("document.getElementById('cited')?.scrollIntoView({block: 'center'})")
                page.screenshot(path=str(out / f"mockup-{name}.png"))
                page.close()
            browser.close()
    finally:
        server.shutdown()
    print(f"screenshots in {out}")


if __name__ == "__main__":
    main()
