"""NFR-REV-02 and NFR-REV-03: the layer's database changes are additive and switch off cleanly."""

import html
import re

import pytest
from fastapi.testclient import TestClient

from controlled_copy.app import create_app
from controlled_copy.governance import MIGRATIONS
from controlled_copy.providers.fake import FakeProvider
from controlled_copy.storage.db import CORE_MIGRATIONS, apply_migrations, connect
from tests.conftest import ACCESS_CODE

pytestmark = [pytest.mark.integration, pytest.mark.stage2]


def schema(conn) -> dict[str, list[tuple]]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'chunk_fts%'"
        )
    ]
    return {t: [tuple(c) for c in conn.execute(f"PRAGMA table_info({t})")] for t in tables}


def test_tc_rev_002_stage2_migrations_only_add_to_a_stage1_database(tmp_path):
    path = tmp_path / "stage1.sqlite3"
    conn = connect(path)
    apply_migrations(conn, CORE_MIGRATIONS)
    conn.execute(
        "INSERT INTO visitor_session VALUES ('s', '2026-10-06T00:00:00+00:00', '2026-10-06T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO notebook (id, session_id, kind, title, created_at) VALUES ('n', 's', 'personal', 'Mine', 'now')"
    )
    before = schema(conn)
    applied = apply_migrations(conn, CORE_MIGRATIONS + MIGRATIONS)
    after = schema(conn)
    assert applied == [m.id for m in MIGRATIONS]
    for table, columns in before.items():
        assert after[table] == columns, f"{table} changed"
    assert set(after) - set(before) == {"seed_vector"}
    assert conn.execute("SELECT title FROM notebook").fetchone()[0] == "Mine"
    conn.close()


def test_tc_rev_002_a_stage2_database_still_serves_the_core_with_the_layer_off(tmp_path, settings):
    on = create_app(settings, FakeProvider(), run_purge=False)
    with TestClient(on) as client:
        client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
        assert "Inbound Operations" in client.get("/app").text
    off = create_app(
        settings.model_copy(update={"feature_governance": False}), FakeProvider(), run_purge=False
    )
    with TestClient(off) as client:
        client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
        page = client.get("/app")
        assert page.status_code == 200


def test_tc_rev_003_switching_the_layer_off_hides_it(settings):
    off = create_app(
        settings.model_copy(update={"feature_governance": False}), FakeProvider(), run_purge=False
    )
    with TestClient(off) as client:
        client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
        page = client.get("/app").text
        assert "Inbound Operations" not in page
        assert "Resolution Card" not in page
        assert "Reset workspace" not in page
        assert client.post("/workspace/reset").status_code in (403, 404, 405)


def test_tc_rev_003_layer_data_is_hidden_after_switching_off(settings):
    on = create_app(settings, FakeProvider(), run_purge=False)
    with TestClient(on) as client:
        client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
        page = client.get("/app").text
        workspace = re.search(r'<option value="([^"]+)"[^>]*>\s*Inbound Operations', page).group(1)
        source = re.search(
            r'name="source_ids" value="([^"]+)"', client.get(f"/app?nb={workspace}").text
        ).group(1)
        cookies = dict(client.cookies)
    off = create_app(
        settings.model_copy(update={"feature_governance": False}), FakeProvider(), run_purge=False
    )
    with TestClient(off, cookies=cookies) as client:
        page = client.get(f"/app?nb={workspace}")
        assert page.status_code == 200 and "Inbound Operations" not in page.text
        assert client.get(f"/sources/{source}").status_code == 404
        csrf = re.search(r'"X-CSRF-Token": "([^"]+)"', html.unescape(page.text)).group(1)
        assert client.delete(f"/notebooks/{workspace}", headers={"X-CSRF-Token": csrf}).status_code == 404


def test_layer_outputs_are_not_half_rendered_with_the_layer_off(settings):
    on = create_app(settings, FakeProvider(), run_purge=False)
    with TestClient(on) as client:
        client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
        page = html.unescape(client.get("/app").text)
        notebook = re.search(r'data-notebook-id="([^"]+)"|/notebooks/([A-Za-z0-9_-]+)/ask', page)
        notebook_id = notebook.group(1) or notebook.group(2)
        csrf = re.search(r'"X-CSRF-Token": "([^"]+)"', page).group(1)
        headers = {"X-CSRF-Token": csrf, "Accept": "application/json"}
        client.post(
            f"/notebooks/{notebook_id}/sources",
            data={"title": "Dock", "text": "Dock 3 opens at six."},
            headers=headers,
        )
        source = re.search(
            r'name="source_ids" value="([^"]+)"', client.get(f"/app?nb={notebook_id}").text
        ).group(1)
        response = client.post(
            f"/notebooks/{notebook_id}/studio/resolution-card",
            data={"situation": "What is the forklift speed limit?", "source_ids": [source]},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        cookies = dict(client.cookies)
    off = create_app(
        settings.model_copy(update={"feature_governance": False}), FakeProvider(), run_purge=False
    )
    with TestClient(off, cookies=cookies) as client:
        page = client.get(f"/app?nb={notebook_id}").text
        assert "made by a feature that is switched off" in page


def test_tc_rev_002_the_stage_1_journey_runs_on_a_migrated_and_seeded_database(settings):
    """Codex Stage 2 review S2-3: not only additive migrations, but the core's paste, ask,
    delete and purge working on a database that went through the layer and its seeding."""
    from datetime import UTC, datetime, timedelta

    from controlled_copy.purge import purge
    from controlled_copy.storage.db import connect
    from controlled_copy.storage.repo import Repo
    from tests.conftest import Visitor
    from tests.helpers.responders import quote_passage_containing

    on = create_app(settings, FakeProvider(), run_purge=False)
    with TestClient(on) as client:
        client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
        assert "Inbound Operations" in client.get("/app").text  # migrated and seeded
    fake = FakeProvider()
    off = create_app(settings.model_copy(update={"feature_governance": False}), fake, run_purge=False)
    with TestClient(off) as client:
        visitor = Visitor(client).login()
        visitor.paste("Dock rule", "Wet cartons go to quarantine area Q-01 at once.")
        fake.responder = quote_passage_containing("Wet cartons go to quarantine area Q-01")
        answer = visitor.ask("Where do wet cartons go?")
        assert answer.status_code == 200 and answer.json()["answer"]["kind"] == "answer"
        deleted = client.delete(f"/sources/{visitor.sources[0]}", headers=visitor.json_headers())
        assert deleted.status_code == 200
    conn = connect(settings.db_path)
    try:
        result = purge(
            settings, Repo(conn), datetime.now(UTC) + timedelta(hours=settings.retention_hours + 1)
        )
        assert result.sessions == 2
        assert conn.execute("SELECT COUNT(*) FROM notebook").fetchone()[0] == 0, "workspace copies purged too"
        assert conn.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 0
    finally:
        conn.close()
