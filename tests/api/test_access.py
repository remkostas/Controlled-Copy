"""FR-ACC-01 to FR-ACC-04."""

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from controlled_copy.app import create_app
from controlled_copy.config import AppMode, Settings
from controlled_copy.providers.fake import FakeProvider
from tests.conftest import ACCESS_CODE

pytestmark = [pytest.mark.api, pytest.mark.stage1]

PUBLIC = {"/", "/access", "/video", "/healthz"}


def test_tc_acc_001_landing_and_video_pages_are_public(app):
    with TestClient(app) as client:
        landing = client.get("/")
        assert landing.status_code == 200
        assert 'name="code"' in landing.text
        assert "Do not upload personal or confidential documents" in landing.text
        assert "Hetzner" in landing.text and "OpenRouter" in landing.text
        assert "7 days" in landing.text
        assert client.get("/video").status_code == 200
        assert client.get("/healthz").json() == {"status": "ok"}


def test_tc_acc_002_correct_code_sets_a_hardened_cookie_and_redirects(tmp_path):
    settings = Settings(
        _env_file=None,
        app_mode=AppMode.DEPLOY,
        app_access_code=ACCESS_CODE,
        app_secret_key="d" * 40,
        model_provider="openrouter",
        openrouter_api_key="not-a-real-key",
        data_dir=tmp_path,
    )
    app = create_app(settings, FakeProvider(), run_purge=False)
    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/app"
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith("cc_session=")
    for attribute in ("httponly", "secure", "samesite=lax", "path=/", "max-age=604800"):
        assert attribute in cookie


def test_tc_acc_003_wrong_codes_are_rejected_and_rate_limited(app):
    with TestClient(app) as client:
        statuses = [client.post("/access", data={"code": f"wrong-{i}"}).status_code for i in range(11)]
        assert statuses[:10] == [401] * 10
        assert statuses[10] == 429
        # Even the right code is refused while the address is blocked.
        assert client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False).status_code == 429


def test_tc_acc_004_all_workspace_routes_need_a_session(app):
    from controlled_copy.web.routes import router

    all_routes = list(router.routes) + [r for layer in app.state.registry.routers for r in layer.routes]
    routes = [r for r in all_routes if isinstance(r, APIRoute) and r.path not in PUBLIC]
    assert len(routes) >= 9
    with TestClient(app) as client:
        for route in routes:
            path = (
                route.path.replace("{notebook_id}", "nb")
                .replace("{source_id}", "src")
                .replace("{template_id}", "briefing")
            )
            for method in route.methods:
                response = client.request(method, path, follow_redirects=False)
                assert response.status_code in (303, 401), f"{method} {path} -> {response.status_code}"
                if response.status_code == 303:
                    assert response.headers["location"] == "/"
                assert len(response.content) < 200, "no data in the response"
    # A forged cookie is no better than none.
    with TestClient(app, cookies={"cc_session": "forged.signature"}) as client:
        assert client.get("/app", follow_redirects=False).status_code == 303
