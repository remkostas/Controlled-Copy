"""FR-MOD-01 to FR-MOD-03 in a real browser (stage 3, fake model)."""

import pytest

from tests.e2e.test_journey_a import CONTRAST_JS, SOP, ask, login, upload

pytestmark = [pytest.mark.e2e, pytest.mark.stage3]

LITE = "google/gemini-3.5-flash-lite"


@pytest.fixture
def settings(settings):
    return settings.model_copy(update={"feature_model_picker": True})


def test_tc_ui_005_choose_a_model_and_see_it_on_the_answer(page, server_url, fake):
    login(page, server_url)
    assert page.input_value("#model-select") == "openai/gpt-6-luna"
    page.select_option("#model-select", LITE)
    page.wait_for_selector("#toast:has-text('Gemini 3.5 Flash Lite')")
    upload(page, SOP)
    page.wait_for_selector(".source")
    turn = ask(page, "What is the purpose of the procedure?")
    assert turn.locator(".answer__model").inner_text() == "gemini-3.5-flash-lite"
    assert [c.model for c in fake.chat_calls if c.schema_name == "answer"] == [LITE]
    page.reload()
    assert page.input_value("#model-select") == LITE, "the choice is kept for the session"
    assert page.evaluate(CONTRAST_JS) == []
    assert page.js_errors == []
