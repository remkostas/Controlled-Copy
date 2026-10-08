"""FR-UI-01, FR-UI-02, FR-ANS-08, NFR-UI-01 in a real browser."""

from pathlib import Path

import pytest

from tests.conftest import ACCESS_CODE, CORPUS
from tests.e2e.conftest import confirm

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]

SOP = CORPUS / "SOP-INB-001_inbound-receiving_rev3.md"

CONTRAST_JS = Path(__file__).with_name("contrast.js").read_text()


def login(page, server_url):
    page.goto(server_url + "/")
    page.fill("#access-code", ACCESS_CODE)
    page.click("button[type=submit]")
    page.wait_for_url("**/app")


def upload(page, path: Path):
    page.set_input_files("input[type=file]", str(path))
    page.wait_for_selector(f".source__title:has-text('{path.stem[:10]}'), .source__title", state="visible")


def ask(page, question: str):
    turns_before = page.locator("#chat-inner article.turn:not(#pending-turn)").count()
    page.fill("#question", question)
    page.press("#question", "Enter")
    turn = page.locator("#chat-inner article.turn:not(#pending-turn)").nth(turns_before)
    turn.wait_for()
    return turn


def test_tc_ui_001_three_panel_layout_on_1366x768(page, server_url):
    login(page, server_url)
    boxes = {}
    for name in ("sources", "chat", "studio"):
        locator = page.locator(f".panel--{name}")
        assert locator.is_visible()
        boxes[name] = locator.bounding_box()
    assert boxes["sources"]["x"] < boxes["chat"]["x"] < boxes["studio"]["x"]
    for box in boxes.values():
        assert box["x"] >= 0 and box["x"] + box["width"] <= 1366 + 1
        assert box["height"] > 600
    assert boxes["chat"]["width"] > boxes["sources"]["width"]
    assert page.locator(".appfoot__note").is_visible()
    assert page.js_errors == []


def test_tc_ui_002_journey_a_end_to_end(page, server_url):
    login(page, server_url)
    # Create a notebook.
    page.click("button[data-toggle='new-notebook']")
    page.fill("#new-notebook-title", "Receiving test")
    page.click("#new-notebook button[type=submit]")
    page.wait_for_selector("h1:has-text('Receiving test')")
    # Upload a source.
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    assert page.locator(".source").count() == 1
    # Ask; the answer has citation chips.
    answer = ask(page, "What is the purpose of the inbound receiving procedure?")
    assert answer.locator(".answer").is_visible()
    chip = answer.locator("button.cite").first
    assert chip.is_visible()
    # Open the citation: the viewer replaces the source list and shows the highlighted passage.
    chip.click()
    page.wait_for_selector("#viewer-slot mark#cited")
    assert page.locator("mark#cited").is_visible()
    assert page.locator(".workspace.is-reading").count() == 1
    page.click("[data-close-viewer]")
    page.wait_for_selector("#source-browser", state="visible")
    # Follow-up: the rewritten question is shown.
    follow_up = ask(page, "and who maintains it?")
    assert follow_up.locator(".searched").is_visible()
    # Refusal for an unsupported question.
    refusal = ask(page, "What is the forklift speed limit in the yard?")
    assert refusal.locator(".refusal").is_visible()
    assert "Not in the selected sources" in refusal.inner_text()
    # Studio Briefing.
    page.click(".studio-action:has-text('Briefing')")
    page.locator("#output-reader").wait_for()  # open large over the chat, closed in Studio
    assert page.locator("#studio-outputs .output__section h3").count() == 4
    # Delete the source, confirmed in the app's dialog.
    page.click(".source__delete")
    confirm(page, "Delete")
    page.wait_for_selector(".empty:has-text('No sources yet')")
    assert page.locator(".source").count() == 0
    assert page.locator("text=Answer removed").count() >= 1
    assert page.js_errors == []


def test_tc_ans_008_citation_chip_opens_the_passage(page, server_url):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source")
    answer = ask(page, "What is the purpose of the procedure?")
    chip = answer.locator("button.cite").first
    label = chip.get_attribute("title")
    chip.click()
    mark = page.locator("#viewer-slot mark#cited")
    mark.wait_for()
    assert mark.is_visible()
    box = mark.bounding_box()
    assert box and 0 <= box["y"] <= 768, "the highlighted passage is scrolled into view"
    viewer_text = page.locator("#viewer-slot").inner_text()
    assert "SOP-INB-001" in viewer_text
    assert label.split(" · ")[-1] in viewer_text
    assert page.js_errors == [], page.js_errors


def test_tc_ui_003_text_meets_wcag_aa_contrast(page, server_url):
    page.goto(server_url + "/")
    # The check must be able to fail: a light-grey probe on paper is reported.
    page.evaluate(
        "() => { const p = document.createElement('p'); p.id = 'probe'; p.textContent = 'low contrast probe';"
        " p.style.color = '#bbbbbb'; document.querySelector('.sheet').appendChild(p); }"
    )
    assert any("low contrast probe" in f for f in page.evaluate(CONTRAST_JS))
    page.evaluate("() => document.getElementById('probe').remove()")
    failures = page.evaluate(CONTRAST_JS)
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source")
    answer = ask(page, "What is the purpose of the procedure?")
    ask(page, "What is the forklift speed limit in the yard?")
    page.click(".studio-action:has-text('Briefing')")
    page.locator("#output-reader").wait_for()
    failures += page.evaluate(CONTRAST_JS)  # with the Briefing open in the reading view
    page.click("[data-reader-close]")
    answer.locator("button.cite").first.click()
    page.wait_for_selector("#viewer-slot mark#cited")
    failures += page.evaluate(CONTRAST_JS)
    assert failures == [], "\n".join(failures[:20])


def test_tc_ui_002_a_failed_paste_keeps_the_text_and_shows_the_error(page, server_url, fake):
    from controlled_copy.providers.base import ProviderError

    def broken(texts, *, model):
        raise ProviderError("embedding down")

    fake.embed = broken
    login(page, server_url)
    page.click("button[data-toggle='paste-form']")
    page.fill("#paste-title", "Handover")
    page.fill("#paste-text", "Dock 3 is closed until Friday.")
    page.click("#paste-form button[type=submit]")
    page.wait_for_selector("#add-source-status .notice--error")
    assert "embedding provider is not available" in page.inner_text("#add-source-status")
    assert page.input_value("#paste-text") == "Dock 3 is closed until Friday."
    assert page.locator("#paste-form").is_visible()


def test_tc_ui_002_a_failed_question_keeps_the_question(page, server_url, fake, settings):
    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source")
    fake.failing_models = {settings.model_generation, settings.model_generation_fallback}
    page.fill("#question", "What is the purpose of the procedure?")
    page.press("#question", "Enter")
    page.wait_for_selector("#chat-inner .notice--error")
    assert page.input_value("#question") == "What is the purpose of the procedure?"
