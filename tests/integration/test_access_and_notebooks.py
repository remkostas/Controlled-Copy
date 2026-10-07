"""FR-ACC-05 session scoping; FR-NB-03 notebook deletion."""

import pytest

from tests.helpers.pdf import make_pdf

pytestmark = [pytest.mark.integration, pytest.mark.stage1]


def test_tc_acc_005_data_is_scoped_to_the_session(make_visitor):
    alice, bob = make_visitor(), make_visitor()
    alice.paste(
        "Alice notes", "The canary ALICECANARY appears only in Alice's notebook about receiving docks."
    )
    bob.paste("Bob notes", "The canary BOBCANARY appears only in Bob's notebook about receiving docks.")
    alice_source = alice.sources[0]

    # Listing: Bob's workspace never shows Alice's data.
    assert "ALICECANARY" not in bob.refresh().page and "Alice notes" not in bob.page
    # Viewing, deleting, asking and searching with a foreign ID: 404, nothing leaks.
    assert bob.client.get(f"/sources/{alice_source}").status_code == 404
    assert bob.client.delete(f"/sources/{alice_source}", headers=bob.json_headers()).status_code == 404
    response = bob.ask(
        "ALICECANARY receiving docks", source_ids=[alice_source], notebook_id=alice.notebook_id
    )
    assert response.status_code == 404
    response = bob.ask("ALICECANARY receiving docks", source_ids=[alice_source])
    assert response.status_code == 422  # Alice's source is not in Bob's notebook
    response = bob.ask("canary receiving docks")
    assert "ALICECANARY" not in response.text
    assert bob.client.get(f"/app?nb={alice.notebook_id}").text.count("Alice notes") == 0
    # Alice still has everything.
    assert alice.client.get(f"/sources/{alice_source}").status_code == 200


def test_tc_nb_003_deleting_a_notebook_removes_everything_in_it(visitor, db, settings):
    visitor.upload("guide.pdf", make_pdf(["Receiving guide page one about docks and pallets."]))
    chunk_ids_before = [
        r[0]
        for r in db.execute(
            "SELECT c.id FROM chunk c JOIN source s ON s.id = c.source_id WHERE s.notebook_id = ?",
            (visitor.notebook_id,),
        )
    ]
    visitor.paste("Notes", "Pallets are counted at the dock before posting the goods receipt.")
    assert visitor.ask("How are pallets counted at the dock?").status_code == 200
    assert visitor.briefing().status_code == 200
    files = list(settings.uploads_dir.iterdir())
    assert len(files) == 1

    response = visitor.client.delete(f"/notebooks/{visitor.notebook_id}", headers=visitor.json_headers())
    assert response.status_code == 200
    for table in ("notebook", "source", "chunk", "chunk_vector", "chat_message", "studio_output"):
        column = (
            "id"
            if table == "notebook"
            else "notebook_id"
            if table in ("source", "chat_message", "studio_output")
            else None
        )
        if column:
            assert (
                db.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (visitor.notebook_id,)
                ).fetchone()[0]
                == 0
            )
    chunk_ids = [
        r[0]
        for r in db.execute(
            "SELECT c.id FROM chunk c JOIN source s ON s.id = c.source_id WHERE s.notebook_id = ?",
            (visitor.notebook_id,),
        )
    ]
    assert chunk_ids == []
    marks = ",".join("?" * len(chunk_ids_before))
    for table, column in (("chunk", "id"), ("chunk_vector", "chunk_id"), ("chunk_fts", "rowid")):
        assert (
            db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} IN ({marks})", chunk_ids_before
            ).fetchone()[0]
            == 0
        )
    assert list(settings.uploads_dir.iterdir()) == []
