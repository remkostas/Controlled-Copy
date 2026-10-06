"""A real uvicorn server (fake model provider) and a headless Chromium for end-to-end tests."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from controlled_copy.app import create_app


@pytest.fixture(scope="session")
def browser() -> Iterator[object]:
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None
        try:
            browser = playwright.chromium.launch(executable_path=executable)
        except playwright_api.Error as exc:
            # A fresh checkout has the package but not the browser. CI installs it, so there a
            # missing browser stays an error instead of a quiet skip.
            if os.environ.get("CI") or "Executable doesn't exist" not in str(exc):
                raise
            pytest.skip("Chromium for Playwright is missing: run `python -m playwright install chromium`")
        yield browser
        browser.close()


@pytest.fixture
def server_url(settings, fake) -> Iterator[str]:
    app = create_app(settings, fake, run_purge=False)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def page(browser, server_url):
    # Reduced motion makes CSS transitions instant, so style checks never sample a colour mid-transition.
    context = browser.new_context(viewport={"width": 1366, "height": 768}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(15000)
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("dialog", lambda dialog: dialog.accept())
    page.js_errors = errors
    yield page
    context.close()
