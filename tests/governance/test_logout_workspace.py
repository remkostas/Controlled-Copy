"""FR-ACC-06 with the governed layer: log out also deletes the visitor's Inbound Operations
copy, its sources, chunks and cards, and nothing of another visitor (stage 2)."""

import pytest

from tests.governance.conftest import Workspace

pytestmark = [pytest.mark.integration, pytest.mark.stage2]


def counts(db, notebook_id: str) -> dict[str, int]:
    one = lambda sql: db.execute(sql, (notebook_id,)).fetchone()[0]  # noqa: E731
    return {
        "notebook": one("SELECT COUNT(*) FROM notebook WHERE id = ?"),
        "sources": one("SELECT COUNT(*) FROM source WHERE notebook_id = ?"),
        "chunks": one(
            "SELECT COUNT(*) FROM chunk c JOIN source s ON s.id = c.source_id WHERE s.notebook_id = ?"
        ),
        "outputs": one("SELECT COUNT(*) FROM studio_output WHERE notebook_id = ?"),
    }


def test_tc_acc_006_log_out_deletes_the_demo_copy_too(make_visitor, db):
    alice, bob = make_visitor(), make_visitor()
    mine, theirs = Workspace(alice), Workspace(bob)
    mine.card("A delivery contains 96 units, but the purchase order expects 100.")
    before = counts(db, mine.id)
    assert before["sources"] == 8 and before["chunks"] > 0 and before["outputs"] == 1
    session_id = db.execute("SELECT session_id FROM notebook WHERE id = ?", (mine.id,)).fetchone()[0]

    alice.client.post("/logout", headers={**alice.headers, "HX-Request": "true"})

    assert counts(db, mine.id) == {"notebook": 0, "sources": 0, "chunks": 0, "outputs": 0}
    assert db.execute("SELECT COUNT(*) FROM visitor_session WHERE id = ?", (session_id,)).fetchone()[0] == 0
    assert counts(db, theirs.id)["sources"] == 8, "another visitor's copy is untouched"
