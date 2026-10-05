"""NFR-REV-02 and NFR-REV-03: the layer's database changes are additive and switch off cleanly."""

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
