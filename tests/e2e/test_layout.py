"""FR-UI-01, FR-ANS-08: the page never scrolls, only the panels; a citation lands on its passage
the first time, also while the reading column is still widening (normal motion, not reduced)."""

import pytest

from tests.conftest import ACCESS_CODE

pytestmark = [pytest.mark.e2e, pytest.mark.stage1]

FILLER = "This paragraph is filler text about general warehouse housekeeping and nothing else."
TARGET = "Rule ZPH-552 says that every pallet is wrapped twice before storage."
OVERFLOW = """() => ({doc: document.documentElement.scrollHeight, win: innerHeight, y: scrollY})"""


@pytest.fixture
def long_source(tmp_path):
    paragraphs = [f"{FILLER} Paragraph {n}." for n in range(1, 61)]
    paragraphs.insert(52, TARGET)
    path = tmp_path / "long-guide.txt"
    path.write_text("\n\n".join(paragraphs), encoding="utf-8")
    return path


def open_page(browser, server_url, width, height):
    """A page with normal motion: the reading column animates as it does for visitors."""
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.set_default_timeout(15000)
    page.goto(server_url + "/")
    page.fill("#access-code", ACCESS_CODE)
    page.click("button[type=submit]")
    page.wait_for_url("**/app")
    return context, page


def cite_target(page, long_source):
    page.set_input_files("input[type=file]", str(long_source))
    page.wait_for_selector(".source", state="attached")  # hidden behind a tab on narrow screens
    page.fill("#question", "What does rule ZPH-552 say?")
    page.press("#question", "Enter")
    chip = page.locator("#chat-inner article.turn:not(#pending-turn) button.cite").first
    chip.wait_for()
    chip.click()
    page.wait_for_selector("#viewer-slot mark#cited")
    page.wait_for_timeout(700)  # longer than the column animation


def in_panel_view(page) -> bool:
    return page.evaluate(
        """() => { const m = document.querySelector('mark#cited').getBoundingClientRect();
                   const b = document.querySelector('#sources-panel .panel__body').getBoundingClientRect();
                   return m.top >= b.top && m.bottom <= b.bottom; }"""
    )


@pytest.mark.parametrize(("width", "height"), [(1366, 768), (880, 700), (390, 844)])
def test_tc_ui_001_the_page_never_scrolls_only_the_panels(browser, server_url, long_source, width, height):
    context, page = open_page(browser, server_url, width, height)
    try:
        cite_target(page, long_source)
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(200)
        m = page.evaluate(OVERFLOW)
        assert m["doc"] <= m["win"] + 1, f"the page is {m['doc']} px for a {m['win']} px window"
        assert m["y"] == 0
    finally:
        context.close()


def test_tc_ans_008_the_first_click_lands_on_the_passage(browser, server_url, long_source):
    context, page = open_page(browser, server_url, 1366, 768)
    try:
        cite_target(page, long_source)
        assert in_panel_view(page), "the cited passage is in view after the first click"
    finally:
        context.close()


def test_tc_ans_008_the_way_back_stays_in_reach(browser, server_url, long_source):
    context, page = open_page(browser, server_url, 1366, 768)
    try:
        cite_target(page, long_source)
        page.evaluate(
            "() => { const b = document.querySelector('#sources-panel .panel__body'); b.scrollTop = b.scrollHeight; }"
        )
        page.wait_for_timeout(100)
        back = page.locator("[data-close-viewer]")
        assert back.is_visible()
        box = back.bounding_box()
        panel = page.locator("#sources-panel .panel__body").bounding_box()
        assert box["y"] >= panel["y"] - 1 and box["y"] + box["height"] <= panel["y"] + panel["height"], (
            "the back button stays inside the visible panel after scrolling down"
        )
    finally:
        context.close()


def test_tc_ans_008_a_child_transition_does_not_settle_the_viewer_early(browser, server_url, long_source):
    context, page = open_page(browser, server_url, 1366, 768)
    try:
        # A hover colour ending inside the workspace while the column still widens.
        page.evaluate(
            """() => document.querySelector('.workspace').addEventListener('click', () => {
                 setTimeout(() => document.querySelector('.panel--chat').dispatchEvent(
                   new TransitionEvent('transitionend', {bubbles: true, propertyName: 'background-color'})), 30);
               }, true)"""
        )
        cite_target(page, long_source)
        assert in_panel_view(page), "the cited passage is in view after the column has settled"
    finally:
        context.close()


@pytest.fixture
def wrapping_source(tmp_path):
    """Long paragraphs that rewrap while the reading column widens, so the passage moves."""
    long_filler = " ".join([FILLER] * 6)
    paragraphs = [f"{long_filler} Paragraph {n}." for n in range(1, 41)]
    paragraphs.insert(32, f"{TARGET} {long_filler}")
    path = tmp_path / "wrapping-guide.txt"
    path.write_text("\n\n".join(paragraphs), encoding="utf-8")
    return path


@pytest.mark.parametrize("dwell_ms", [0, 100, 120])
def test_tc_ans_008_a_hovered_chip_still_lands_on_the_passage(browser, server_url, wrapping_source, dwell_ms):
    """A real hover before the click starts the chip's colour transitions; their end events
    must not settle the viewer before the column has its final width."""
    context, page = open_page(browser, server_url, 1366, 768)
    try:
        page.set_input_files("input[type=file]", str(wrapping_source))
        page.wait_for_selector(".source", state="attached")
        page.fill("#question", "What does rule ZPH-552 say?")
        page.press("#question", "Enter")
        chip = page.locator("#chat-inner article.turn:not(#pending-turn) button.cite").first
        chip.wait_for()
        chip.hover()
        page.wait_for_timeout(dwell_ms)
        chip.click()
        page.wait_for_selector("#viewer-slot mark#cited")
        page.wait_for_timeout(700)
        assert in_panel_view(page), f"passage in view after a {dwell_ms} ms hover"
    finally:
        context.close()


def test_tc_ui_001_a_long_unbroken_question_does_not_widen_the_chat(page, server_url):
    """Round 2: 1,500 characters without a space pushed the refusal past the chat panel."""
    from tests.e2e.test_journey_a import SOP, login, upload

    login(page, server_url)
    upload(page, SOP)
    page.wait_for_selector(".source .badge:has-text('SOP-INB-001')")
    page.fill("#question", "a" * 1500)
    page.press("#question", "Enter")
    page.locator("#chat-inner article.turn:not(#pending-turn)").first.wait_for()
    log = page.evaluate(
        "() => { const l = document.querySelector('#chat-log'); return [l.scrollWidth, l.clientWidth]; }"
    )
    assert log[0] <= log[1] + 1, f"the chat scrolls sideways: {log}"
    assert page.js_errors == []
