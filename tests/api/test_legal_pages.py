"""FR-LEG-01 and FR-LEG-02: a privacy notice and an Impressum link, reachable without logging in
and from every page (stage 1)."""

import pytest
from fastapi.testclient import TestClient

from controlled_copy.app import create_app
from controlled_copy.config import ConfigError

pytestmark = [pytest.mark.api, pytest.mark.stage1]

IMPRESSUM = "https://www.example.org/impressum"


@pytest.fixture
def settings(settings):
    return settings.model_copy(
        update={
            "operator_name": "Erika Muster",
            "operator_email": "erika@example.org",
            "impressum_url": IMPRESSUM,
        }
    )


def test_tc_leg_001_privacy_notice_is_public_and_names_the_controller(app):
    page = TestClient(app).get("/privacy")
    assert page.status_code == 200
    text = page.text
    for expected in (
        "Privacy notice",
        "Erika Muster",
        "erika@example.org",
        "Art. 6 (1) (f) GDPR",
        "OpenRouter",
        "Hetzner",
        "Art. 77",
    ):
        assert expected in text, expected
    assert f'href="{IMPRESSUM}"' in text
    assert page.headers["content-security-policy"].startswith("default-src 'self'")


def test_tc_leg_001_privacy_notice_states_the_configured_retention(settings, fake):
    app = create_app(settings.model_copy(update={"retention_hours": 72}), fake, run_purge=False)
    assert "deleted 3 days after your last visit" in TestClient(app).get("/privacy").text


def test_tc_leg_002_every_page_links_privacy_and_impressum(app, visitor):
    pages = [
        TestClient(app).get("/").text,
        TestClient(app).get("/video").text,
        visitor.client.get("/app").text,
    ]
    for page in pages:
        assert 'href="/privacy"' in page
        assert f'href="{IMPRESSUM}"' in page


def test_tc_leg_002_no_impressum_link_without_a_url(settings, fake):
    app = create_app(settings.model_copy(update={"impressum_url": None}), fake, run_purge=False)
    page = TestClient(app).get("/").text
    assert 'href="/privacy"' in page and "Impressum" not in page


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "http://example.org/impressum", "https://", "https://exa mple.org"]
)
def test_tc_leg_002_impressum_url_must_be_https(settings, url):
    with pytest.raises(ConfigError, match="IMPRESSUM_URL"):
        settings.model_copy(update={"impressum_url": url}).check_startup()


def test_tc_leg_002_operator_email_must_be_an_address(settings):
    with pytest.raises(ConfigError, match="OPERATOR_EMAIL"):
        settings.model_copy(update={"operator_email": "not an address"}).check_startup()
