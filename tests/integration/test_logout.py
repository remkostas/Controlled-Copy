"""FR-ACC-06: log out ends the anonymous session and deletes its data now."""

import pytest

from tests.conftest import corpus_file

pytestmark = [pytest.mark.integration, pytest.mark.stage1]


def test_tc_acc_006_log_out_deletes_the_session_and_its_data(make_visitor, db, settings):
    alice, bob = make_visitor(), make_visitor()
    alice.upload("sop.md", corpus_file("SOP-INB-001_inbound-receiving_rev3.md"))
    alice.ask("What is the purpose of the procedure?")
    bob.paste("Kept", "Bob's note stays where it is.")
    files = [r["file_path"] for r in db.execute("SELECT file_path FROM source WHERE file_path IS NOT NULL")]
    chunk_ids = [
        r[0]
        for r in db.execute(
            "SELECT c.id FROM chunk c JOIN source s ON s.id = c.source_id WHERE s.notebook_id = ?",
            (alice.notebook_id,),
        )
    ]
    assert chunk_ids
    assert files and all((settings.uploads_dir / f).exists() for f in files)

    response = alice.client.post("/logout", headers={**alice.headers, "HX-Request": "true"})
    assert response.status_code == 200 and response.headers["HX-Redirect"] == "/"
    assert "cc_session=" in response.headers["set-cookie"] and "Max-Age=0" in response.headers["set-cookie"]

    assert alice.client.get("/app", follow_redirects=False).status_code in (302, 303, 401)
    assert db.execute("SELECT COUNT(*) FROM notebook WHERE id = ?", (alice.notebook_id,)).fetchone()[0] == 0
    assert (
        db.execute(
            "SELECT COUNT(*) FROM chat_message WHERE notebook_id = ?", (alice.notebook_id,)
        ).fetchone()[0]
        == 0
    )
    assert not any((settings.uploads_dir / f).exists() for f in files), "uploaded files are removed"
    marks = ",".join("?" * len(chunk_ids))
    assert (
        db.execute(f"SELECT COUNT(*) FROM chunk_fts WHERE rowid IN ({marks})", chunk_ids).fetchone()[0] == 0
    )
    assert db.execute("SELECT COUNT(*) FROM notebook WHERE id = ?", (bob.notebook_id,)).fetchone()[0] == 1


def test_tc_acc_006_the_workspace_offers_log_out(visitor):
    assert 'hx-post="/logout"' in visitor.refresh().page
