"""FR-MOD-01 to FR-MOD-05: visitors choose the generation model from the allowlist (stage 3)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from controlled_copy.app import create_app
from controlled_copy.config import ConfigError
from controlled_copy.providers.fake import FakeProvider
from tests.conftest import ACCESS_CODE, Visitor, corpus_file
from tests.helpers.responders import quote_passage_containing

pytestmark = [pytest.mark.integration, pytest.mark.stage3]

LUNA, PRO, LITE = "openai/gpt-6-luna", "openai/gpt-6-luna-pro", "google/gemini-3.5-flash-lite"


@pytest.fixture
def warehouse(visitor):
    visitor.upload(
        "SOP-INB-001_inbound-receiving_rev3.md", corpus_file("SOP-INB-001_inbound-receiving_rev3.md")
    )
    return visitor


def choose(visitor, model: str, csrf: bool = True):
    headers = visitor.json_headers() if csrf else {"Accept": "application/json"}
    return visitor.client.post("/settings/model", data={"model": model}, headers=headers)


def test_tc_mod_001_the_picker_offers_the_allowlist_with_the_default_selected(visitor):
    page = visitor.client.get("/app").text
    assert 'hx-post="/settings/model"' in page
    for label in ("GPT-6 Luna", "GPT-6 Luna Pro", "Gemini 3.5 Flash Lite"):
        assert label in page
    assert f'<option value="{LUNA}" selected>' in page


def test_tc_mod_002_only_allowlisted_models_can_be_chosen(visitor):
    assert choose(visitor, "mistralai/mistral-small-2603").status_code == 422
    assert choose(visitor, "").status_code == 422
    assert choose(visitor, LITE, csrf=False).status_code == 403
    assert choose(visitor, LITE).json() == {"model": LITE}
    assert f'<option value="{LITE}" selected>' in visitor.client.get("/app").text


def test_tc_mod_003_the_chosen_model_answers_and_is_shown(warehouse, fake):
    fake.responder = quote_passage_containing("Deviations of up to 2% of the ordered quantity")
    choose(warehouse, PRO)
    answer = warehouse.ask("What is the quantity tolerance?").json()["answer"]
    assert [c.model for c in fake.chat_calls] == [PRO]
    assert answer["model"] == PRO and answer["fallback"] is False
    assert '<span class="answer__model"' in warehouse.client.get("/app").text
    assert "gpt-6-luna-pro</span>" in warehouse.client.get("/app").text


def test_tc_mod_004_the_fallback_still_answers_when_the_chosen_model_fails(warehouse, fake, settings):
    fake.responder = quote_passage_containing("Deviations of up to 2% of the ordered quantity")
    fake.failing_models = {PRO}
    choose(warehouse, PRO)
    answer = warehouse.ask("What is the quantity tolerance?").json()["answer"]
    assert [c.model for c in fake.chat_calls] == [PRO, settings.model_generation_fallback]
    assert answer["fallback"] is True
    assert "(fallback)</span>" in warehouse.client.get("/app").text


def test_tc_mod_004_each_visitor_has_their_own_choice(make_visitor, fake):
    alice, bob = make_visitor(), make_visitor()
    choose(alice, LITE)
    assert f'<option value="{LITE}" selected>' in alice.client.get("/app").text
    assert f'<option value="{LUNA}" selected>' in bob.client.get("/app").text


def test_tc_mod_005_a_model_removed_from_the_allowlist_falls_back_to_the_default(settings, fake):
    app = create_app(settings, fake, run_purge=False)
    with TestClient(app) as client:
        visitor = Visitor(client).login()
        choose(visitor, LITE)
        cookies = dict(client.cookies)
    narrowed = create_app(
        settings.model_copy(update={"model_choices": f"{LUNA},{PRO}"}), fake, run_purge=False
    )
    with TestClient(narrowed, cookies=cookies) as client:
        page = client.get("/app").text
        assert f'<option value="{LUNA}" selected>' in page and LITE not in page


@pytest.mark.parametrize(
    ("choices", "problem"),
    [
        (f"{LUNA},{LUNA}", "lists a model twice"),
        (f"{PRO},{LITE}", "must include MODEL_GENERATION"),
        (f"{LUNA},not a model", "OpenRouter model IDs"),
    ],
)
def test_tc_mod_005_the_allowlist_is_checked_at_startup(settings, choices, problem):
    with pytest.raises(ConfigError, match=problem):
        settings.model_copy(update={"model_choices": choices}).check_startup()


def test_tc_rev_003_with_the_picker_off_there_is_no_picker_and_no_route(settings):
    off = create_app(
        settings.model_copy(update={"feature_model_picker": False}), FakeProvider(), run_purge=False
    )
    with TestClient(off) as client:
        client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
        assert "/settings/model" not in client.get("/app").text
        assert client.post("/settings/model", data={"model": LITE}).status_code in (403, 404, 405)


def test_tc_mod_003_the_resolution_card_uses_the_chosen_model_too(settings):
    from tests.governance.conftest import Workspace

    fake = FakeProvider()
    both = create_app(settings.model_copy(update={"feature_governance": True}), fake, run_purge=False)
    with TestClient(both) as client:
        visitor = Visitor(client).login()
        workspace = Workspace(visitor)
        choose(visitor, LITE)
        card = workspace.card("The WMS shows error GR-204 after I scan the delivery.")
        assert card.status_code == 200, card.text
        assert [c.model for c in fake.chat_calls if c.schema_name == "resolution_card"] == [LITE]
        assert "gemini-3.5-flash-lite" in client.get(f"/app?nb={workspace.id}").text
