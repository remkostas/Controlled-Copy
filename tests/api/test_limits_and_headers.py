"""FR-LIM-01 to FR-LIM-03, NFR-SEC-03."""

import pytest

pytestmark = [pytest.mark.api, pytest.mark.stage1]


def test_tc_lim_001_per_visitor_hourly_call_limit(visitor, settings, make_visitor):
    visitor.paste("Doc", "Pallets are wrapped in foil before storage.")  # one embedding call
    settings.model_calls_per_visitor_hour = 6
    statuses = [visitor.ask(f"How are pallets wrapped, variant {i}?").status_code for i in range(4)]
    assert 429 in statuses
    response = visitor.ask("How are pallets wrapped?")
    assert response.status_code == 429
    assert "model calls per hour" in response.json()["error"]
    # Another visitor is not affected by this visitor's limit.
    other = make_visitor()
    other.paste("Doc", "Pallets are wrapped in foil before storage.")
    assert other.ask("How are pallets wrapped?").status_code == 200


def test_tc_lim_002_daily_budget_switches_to_read_only(visitor, settings, db):
    visitor.paste("Doc", "Pallets are wrapped in foil before storage.")
    source_id = visitor.sources[0]
    settings.model_calls_per_day = db.execute("SELECT COUNT(*) FROM model_call").fetchone()[0]
    response = visitor.ask("How are pallets wrapped?")
    assert response.status_code == 503
    assert "daily budget" in response.json()["error"]
    assert visitor.briefing().status_code == 503
    assert visitor.paste("More", "More text.", expect=503).json()["error"].startswith("The demo has reached")
    page = visitor.client.get("/app")
    assert page.status_code == 200 and "daily budget" in page.text and "disabled" in page.text
    assert visitor.client.get(f"/sources/{source_id}").status_code == 200


def test_tc_lim_003_question_length_is_limited_on_client_and_server(visitor):
    visitor.paste("Doc", "Pallets are wrapped in foil before storage.")
    assert 'maxlength="1500"' in visitor.refresh().page
    response = visitor.ask("x" * 1501)
    assert response.status_code == 422
    assert "1,500 characters" in response.json()["error"]
    assert visitor.ask("How are pallets wrapped?" + " " * 10).status_code == 200


def test_tc_sec_003_security_headers_on_every_page(visitor):
    for path in ("/", "/video", "/app", "/static/css/app.css", "/healthz"):
        headers = visitor.client.get(path, follow_redirects=False).headers
        csp = headers["content-security-policy"]
        assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp
        assert "frame-ancestors 'none'" in csp
        assert "http" not in csp, "no third-party origins"
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "same-origin"


def test_tc_sec_003_pages_have_no_inline_scripts_or_styles(visitor):
    import re

    visitor.paste("Doc", "Pallets are wrapped in foil before storage.")
    visitor.ask("How are pallets wrapped?")
    for path in ("/", "/video", "/app"):
        page = visitor.client.get(path).text
        assert re.search(r"<script(?![^>]*\bsrc=)", page) is None
        assert " style=" not in page and "<style" not in page
        assert " on" + "click=" not in page and "hx-on" not in page
