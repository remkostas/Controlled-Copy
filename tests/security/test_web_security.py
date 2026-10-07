"""NFR-SEC-01, NFR-SEC-02, NFR-LOG-01, NFR-SEC-07."""

import logging
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.helpers.pdf import make_pdf
from tests.helpers.responders import answer_with

pytestmark = [pytest.mark.security, pytest.mark.stage1]

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = '<script>alert("x")</script><img src=x onerror=alert(1)>'


def test_tc_sec_001_untrusted_text_never_executes(visitor, fake):
    visitor.paste(f"Title {SCRIPT}", f"Receiving rules. {SCRIPT} Pallets are wrapped in foil before storage.")

    def hostile(passages):
        pid = passages[0][0]
        return {
            "statements": [
                {
                    "text": f"Answer with markup {SCRIPT}",
                    "citations": [{"passage_id": pid, "quote": "Pallets are wrapped in foil"}],
                }
            ],
            "unanswerable": [SCRIPT],
        }

    fake.responder = answer_with(hostile)
    answer_html = visitor.client.post(
        f"/notebooks/{visitor.notebook_id}/ask",
        data={"question": f"How are pallets wrapped? {SCRIPT}", "source_ids": visitor.sources},
        headers={**visitor.headers, "HX-Request": "true"},
    ).text
    page = visitor.refresh().page
    viewer = visitor.client.get(f"/sources/{visitor.sources[0]}", headers={"HX-Request": "true"}).text
    for body in (answer_html, page, viewer):
        assert "<script>alert" not in body
        assert "<img src=x" not in body
        assert "&lt;script&gt;" in body


def test_tc_sec_002_state_changing_requests_need_the_csrf_token(visitor, db):
    visitor.paste("Doc", "Pallets are wrapped in foil before storage.")
    source_id = visitor.sources[0]
    attempts = [
        ("post", "/notebooks", {"data": {"title": "x"}}),
        ("delete", f"/notebooks/{visitor.notebook_id}", {}),
        ("post", f"/notebooks/{visitor.notebook_id}/sources", {"data": {"title": "x", "text": "y"}}),
        ("delete", f"/sources/{source_id}", {}),
        (
            "post",
            f"/notebooks/{visitor.notebook_id}/ask",
            {"data": {"question": "q", "source_ids": [source_id]}},
        ),
        ("post", f"/notebooks/{visitor.notebook_id}/studio/briefing", {"data": {"source_ids": [source_id]}}),
    ]
    for method, path, kwargs in attempts:
        for headers in (
            {},
            {"X-CSRF-Token": "wrong"},
            {"X-CSRF-Token": visitor.csrf, "Origin": "https://evil.example"},
        ):
            response = getattr(visitor.client, method)(path, headers=headers, **kwargs)
            assert response.status_code == 403, f"{method} {path} {headers} -> {response.status_code}"
    assert (
        db.execute("SELECT COUNT(*) FROM source WHERE notebook_id = ?", (visitor.notebook_id,)).fetchone()[0]
        == 1
    )
    assert db.execute("SELECT COUNT(*) FROM notebook WHERE kind = 'personal'").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM chat_message").fetchone()[0] == 0


def test_tc_sec_002_another_sessions_token_is_rejected(make_visitor):
    alice, bob = make_visitor(), make_visitor()
    response = bob.client.post("/notebooks", data={"title": "x"}, headers={"X-CSRF-Token": alice.csrf})
    assert response.status_code == 403


def test_tc_log_001_no_content_in_logs(visitor, fake, caplog, capfd):
    canary = "CANARY7731QX"
    caplog.set_level(logging.DEBUG)
    visitor.paste(f"Title {canary}", f"Pallets are wrapped in foil. The code word is {canary} for this test.")
    visitor.upload("c.pdf", make_pdf([f"PDF text with {canary} inside about pallets."]))
    visitor.upload(
        "c.md", f"---\ndocument_id: {canary}\nstatus: approved\n---\n# {canary}\n\nBody {canary}.".encode()
    )
    visitor.ask(f"What is the code word {canary}?")
    visitor.ask(f"and the pallets {canary}?")
    visitor.briefing()
    visitor.upload("bad.txt", f"{canary}".encode("utf-16"), expect=415)
    fake.failing_models = {
        visitor.client.app.state.settings.model_generation,
        visitor.client.app.state.settings.model_generation_fallback,
    }
    visitor.ask(f"Failing question {canary}?")
    fake.failing_models = set()
    fake.responder = lambda request: f"not json {canary}"
    visitor.ask(f"Malformed output {canary}?")
    captured = capfd.readouterr()
    logged = "\n".join(record.getMessage() for record in caplog.records) + captured.out + captured.err
    assert caplog.records, "logging must actually be captured"
    assert canary not in logged
    assert canary.lower() not in logged.lower()


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks not installed")
def test_tc_sec_007_no_secrets_in_the_repository(tmp_path):
    """Scan every file git would commit (tracked or not ignored), never the ignored .env or data."""
    listed = (
        subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    for name in filter(None, listed):
        source = ROOT / name
        if source.is_file():
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    report = tmp_path.parent / "gitleaks-report.json"
    result = subprocess.run(
        [
            "gitleaks",
            "dir",
            str(tmp_path),
            "--no-banner",
            "--redact",
            "--exit-code",
            "1",
            "--report-format",
            "json",
            "--report-path",
            str(report),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, report.read_text() if report.exists() else result.stderr


def test_tc_sec_002_access_form_rejects_foreign_origins(app):
    from fastapi.testclient import TestClient

    from tests.conftest import ACCESS_CODE

    with TestClient(app) as client:
        response = client.post(
            "/access",
            data={"code": ACCESS_CODE},
            headers={"Origin": "https://evil.example"},
            follow_redirects=False,
        )
        assert response.status_code == 403
        assert "cc_session" not in response.headers.get("set-cookie", "")


def test_tc_sec_002_non_ascii_tokens_are_rejected_cleanly(visitor):
    token = "t\u00f6ken".encode("latin-1")
    response = visitor.client.post("/notebooks", data={"title": "x"}, headers={"X-CSRF-Token": token})
    assert response.status_code == 403
    cookie = "cc_session=abc.\u00e9\u00e9".encode("latin-1")
    fresh = visitor.client.__class__(visitor.client.app)
    assert fresh.get("/app", headers={"Cookie": cookie}, follow_redirects=False).status_code == 303


def test_tc_sec_004_cookie_is_secure_over_https_even_in_local_mode(app):
    from fastapi.testclient import TestClient

    from tests.conftest import ACCESS_CODE

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
    assert "secure" in response.headers["set-cookie"].lower()


def test_tc_sec_004_data_and_uploads_are_private(visitor, settings):
    import stat

    visitor.upload("note.txt", b"Private text about docks.")
    for path in (settings.data_dir, settings.uploads_dir):
        assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0, path
    stored = next(settings.uploads_dir.iterdir())
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600


def test_tc_sec_002_origin_must_match_scheme_too(app):
    from fastapi.testclient import TestClient

    from tests.conftest import ACCESS_CODE

    with TestClient(app, base_url="https://testserver") as client:
        response = client.post(
            "/access",
            data={"code": ACCESS_CODE},
            headers={"Origin": "http://testserver"},
            follow_redirects=False,
        )
    assert response.status_code == 403
