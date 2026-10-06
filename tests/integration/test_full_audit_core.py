"""Regressions for the full audit of 2026-10-06 (reviews/full-audit-2026-10-06), core."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from controlled_copy.app import create_app
from controlled_copy.limits import LimitExceeded
from controlled_copy.providers.fake import FakeProvider
from tests.conftest import Visitor

pytestmark = [pytest.mark.integration, pytest.mark.stage1]


def app_with(settings, fake, **update):
    return create_app(settings.model_copy(update=update), fake, run_purge=False)


# Price caps of 1 USD per million tokens make one call's worst case about 0.01 USD, so the
# tests can count a few calls against small daily limits.
LOW_CAPS = {"max_price_prompt_per_million": 1.0, "max_price_completion_per_million": 1.0}


def test_sec_01_billed_malformed_answers_count_against_the_dollar_limit(settings):
    fake = FakeProvider(cost_per_call=0.04, responder=lambda request: "this is not JSON")
    with TestClient(app_with(settings, fake, max_usd_per_day=0.07, **LOW_CAPS)) as client:
        visitor = Visitor(client).login()
        visitor.paste("Doc", "Deviations of up to 2% of the ordered quantity are posted as counted.")
        failed = visitor.ask("How are deviations of the ordered quantity posted?")
        assert failed.status_code == 502, "both attempts returned malformed output"
        budget = app_state_budget(client)
        assert budget.repo.spent_usd("2000-01-01T00:00:00") >= 0.08, "both billed attempts are counted"
        assert budget.read_only(), "the page shows the daily limit before any new work starts"
        assert visitor.ask("Again?").status_code == 503


def app_state_budget(client):
    from controlled_copy.limits import Budget
    from controlled_copy.storage.db import connect
    from controlled_copy.storage.repo import Repo

    settings = client.app.state.settings
    return Budget(settings, Repo(connect(settings.db_path)))


def test_sec_01_a_timed_out_call_keeps_its_reservation(settings):
    from controlled_copy.limits import worst_case_usd
    from controlled_copy.providers.base import MAX_COMPLETION_TOKENS

    fake = FakeProvider(delay_seconds=2)
    app = app_with(settings, fake, provider_timeout_seconds=0.3)
    with TestClient(app) as client:
        visitor = Visitor(client).login()
        visitor.paste("Doc", "Deviations of up to 2% of the ordered quantity are posted as counted.")
        assert visitor.ask("How are deviations of the ordered quantity posted?").status_code == 504
        spent = app_state_budget(client).repo.spent_usd("2000-01-01T00:00:00")
        smallest = worst_case_usd(0, 3.0, MAX_COMPLETION_TOKENS, 15.0)  # the output allowance alone
        assert spent >= 2 * smallest, "two timed-out attempts keep two worst-case reservations"


def test_sec_01_parallel_calls_cannot_book_past_the_limit(settings, services):
    budget = services.budget
    services.settings.max_usd_per_day = 0.03
    first = budget.consume(None, "answer", reserve_usd=0.02)
    assert first
    with pytest.raises(LimitExceeded):
        budget.consume(None, "answer", reserve_usd=0.02)  # 0.04 would cross 0.03 before settling
    budget.settle(first, 0.001)
    assert budget.consume(None, "answer", reserve_usd=0.02), "room again once the first call settled"


def test_sec_01_racing_calls_on_separate_connections_stay_within_the_limit(settings, services):
    """Full audit re-check RCK-01: two requests on their own database connections reserve at
    the same moment. Only as many calls start as their reservations fit, and while every call
    costs at most its reservation, the day's settled spend stays within the limit."""
    import threading

    from controlled_copy.limits import Budget
    from controlled_copy.storage.db import connect
    from controlled_copy.storage.repo import Repo

    services.settings.max_usd_per_day = 0.05
    reserve, cost = 0.02, 0.019  # the provider honours the caps: cost <= reservation
    start = threading.Barrier(3)
    outcomes: list[str] = []

    def call() -> None:
        budget = Budget(services.settings, Repo(connect(settings.db_path)))
        start.wait()
        try:
            call_id = budget.consume(None, "answer", reserve_usd=reserve)
        except LimitExceeded:
            outcomes.append("refused")
            return
        budget.settle(call_id, cost)
        outcomes.append("ran")

    threads = [threading.Thread(target=call) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(outcomes) == ["ran", "ran", "refused"], "0.06 of reservations do not fit in 0.05"
    assert services.repo.spent_usd("2000-01-01T00:00:00") <= 0.05


def test_sec_01_a_reservation_covers_the_most_a_call_can_cost(settings):
    """The reservation is the worst case under the caps sent with the request: every prompt
    byte as a token at the prompt cap, the whole output allowance at the completion cap."""
    from controlled_copy.limits import worst_case_usd
    from controlled_copy.providers.base import MAX_COMPLETION_TOKENS
    from controlled_copy.providers.openrouter import build_chat_request

    messages = [{"role": "user", "content": "Ä" * 5000}]  # two bytes per character
    request = build_chat_request(messages, {"type": "object"}, "answer", "m", {"prompt": 3, "completion": 15})
    assert request["max_tokens"] == MAX_COMPLETION_TOKENS
    assert request["provider"]["max_price"] == {"prompt": 3, "completion": 15}
    reserve = worst_case_usd(10_000, 3.0, MAX_COMPLETION_TOKENS, 15.0)
    most = (10_000 * 3.0 + MAX_COMPLETION_TOKENS * 15.0) / 1_000_000
    assert reserve >= most


def test_sec_01_a_cost_above_the_reservation_is_recorded_in_full(settings, services):
    """A provider that bills more than the caps allow: the real cost is booked and the day
    turns read-only, it is never capped at the reservation."""
    services.settings.max_usd_per_day = 0.05
    call_id = services.budget.consume(None, "answer", reserve_usd=0.02)
    services.budget.settle(call_id, 0.09)
    assert services.repo.spent_usd("2000-01-01T00:00:00") == pytest.approx(0.09)
    assert services.budget.read_only()


def test_sec_01_embedding_requests_carry_a_price_cap_and_report_their_cost(settings):
    import json

    import httpx

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        usage = {"prompt_tokens": 3, "cost": 0.00002}
        body = {"data": [{"index": 0, "embedding": [0.1, 0.2]}], "usage": usage}
        return httpx.Response(200, json=body)

    provider = _openrouter_with(handler)
    provider.max_price_embedding = 0.1
    result = provider.embed(["one"], model="baai/bge-m3")
    assert seen["provider"]["max_price"] == {"prompt": 0.1}
    assert seen["provider"]["zdr"] is True
    assert result.cost_usd == pytest.approx(0.00002)


def _openrouter_with(handler):
    import httpx

    from controlled_copy.providers.openrouter import OpenRouterProvider

    provider = OpenRouterProvider("not-a-real-key", "https://example.invalid/api/v1", 5.0)
    provider._client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://example.invalid/api/v1"
    )
    return provider


def test_model_01_a_null_message_is_bad_output_with_its_cost_and_the_fallback_answers(services):
    import json

    import httpx
    from pydantic import BaseModel

    from controlled_copy.answering.generate import generate
    from controlled_copy.providers.base import ProviderBadOutput

    class Out(BaseModel):
        ok: bool

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        if model == services.settings.model_generation:
            return httpx.Response(200, json={"choices": [{"message": None}], "usage": {"cost": 0.01}})
        answer = {"choices": [{"message": {"content": '{"ok": true}'}}], "model": model}
        return httpx.Response(200, json=answer)

    provider = _openrouter_with(handler)
    with pytest.raises(ProviderBadOutput) as error:
        primary = services.settings.model_generation
        provider.chat_json([], schema={}, schema_name="x", model=primary, timeout=5)
    assert error.value.cost_usd == 0.01
    services.provider = provider
    messages = [{"role": "user", "content": "q"}]
    payload, result = generate(services, messages, schema={}, schema_name="x", model_cls=Out)
    assert payload.ok is True and result.model == services.settings.model_generation_fallback


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"data": [{"index": 0, "embedding": None}]},
        {"data": [{"index": 0, "embedding": [0.1, float("nan")]}]},
        {"data": ["not an object"]},
    ],
)
def test_model_01_malformed_embeddings_are_bad_output(body):
    import httpx

    from controlled_copy.providers.base import ProviderBadOutput

    provider = _openrouter_with(lambda request: httpx.Response(200, content=__import__("json").dumps(body)))
    with pytest.raises(ProviderBadOutput):
        provider.embed(["one"], model="baai/bge-m3")


def test_sec_02_a_visitor_cannot_store_more_than_their_share(settings):
    fake = FakeProvider()
    with TestClient(app_with(settings, fake, max_visitor_upload_mb=1)) as client:
        visitor = Visitor(client).login()
        visitor.upload("first.txt", ("pallet " * 90_000).encode())  # about 630 KB
        embeds = fake.embed_calls
        refused = visitor.upload("second.txt", ("carton " * 90_000).encode(), expect=409)
        assert "most this demo stores per visitor (1 MB)" in refused.json()["error"]
        assert fake.embed_calls == embeds, "refused before any embedding call"


def test_sec_02_the_demo_as_a_whole_has_a_storage_limit(settings, make_visitor):
    with TestClient(app_with(settings, FakeProvider(), max_total_upload_mb=1)) as client:
        Visitor(client).login().upload("first.txt", ("pallet " * 90_000).encode())
    with TestClient(app_with(settings, FakeProvider(), max_total_upload_mb=1)) as client:
        refused = Visitor(client).login().upload("second.txt", ("carton " * 90_000).encode(), expect=507)
        assert "storage is full" in refused.json()["error"]


def test_sec_02_nothing_is_accepted_when_the_disk_runs_low(settings, monkeypatch):
    import shutil
    from collections import namedtuple

    from controlled_copy.storage import repo

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(repo.shutil, "disk_usage", lambda path: usage(10, 9, 5 * 1024 * 1024))
    assert shutil.disk_usage  # the real function is untouched outside the module
    fake = FakeProvider()
    with TestClient(app_with(settings, fake, min_free_disk_mb=100)) as client:
        visitor = Visitor(client).login()
        embeds = fake.embed_calls  # a layer may seed its workspace at login
        assert visitor.paste("Note", "A short note about docks.", expect=507).status_code == 507
        assert fake.embed_calls == embeds, "refused before any embedding call"


def test_sec_02_a_disk_that_fills_during_embedding_refuses_the_write(settings, monkeypatch):
    """Full audit re-check RCK-04: free space is checked again inside the write, with what
    the insert adds to the database, so space lost while the embeddings ran counts."""
    from collections import namedtuple

    from controlled_copy.storage import repo

    usage = namedtuple("usage", "total used free")
    free = {"bytes": 101 * 1024 * 1024}
    monkeypatch.setattr(repo.shutil, "disk_usage", lambda path: usage(10, 9, free["bytes"]))

    class FillingDisk(FakeProvider):
        def embed(self, texts, *, model):
            free["bytes"] = 5 * 1024 * 1024  # another process wrote to the volume meanwhile
            return super().embed(texts, model=model)

    fake = FillingDisk()
    with TestClient(app_with(settings, fake, min_free_disk_mb=100)) as client:
        visitor = Visitor(client).login()
        free["bytes"] = 101 * 1024 * 1024
        refused = visitor.upload("note.txt", b"A short note about docks.", expect=507)
        assert "storage is full" in refused.json()["error"]
        db = client.app.state.settings.db_path
        from controlled_copy.storage.db import connect

        assert connect(db).execute("SELECT COUNT(*) FROM source").fetchone()[0] == 0, "nothing stored"
        uploads = client.app.state.settings.uploads_dir
        assert not uploads.exists() or not any(uploads.iterdir()), "the uploaded file was removed again"


def test_sec_02_the_storage_limit_is_rechecked_inside_the_write(visitor, services, db):
    from controlled_copy.storage.repo import CapacityReached, NewSource

    visitor.upload("first.txt", ("pallet " * 90_000).encode())
    sid = db.execute("SELECT session_id FROM notebook WHERE id = ?", (visitor.notebook_id,)).fetchone()[0]
    notebook = services.repo.get_notebook(sid, visitor.notebook_id)
    late = NewSource(
        notebook=notebook,
        title="Arrived in parallel",
        kind="paste",
        bytes=600_000,
        text="x",
        pages=None,
        page_starts=None,
        warnings=[],
        metadata=None,
        metadata_origin="none",
        file_path=None,
        chunks=[],
        vectors=[],
        vector_model="fake",
    )
    with pytest.raises(CapacityReached):
        services.repo.insert_source(late, storage_limits_mb=(1, 5000))


def test_sec_03_a_blocked_checkpoint_is_reported_and_completed_by_the_purge(visitor, settings):
    import time

    from controlled_copy.purge import purge
    from controlled_copy.storage.db import connect
    from controlled_copy.storage.repo import Repo

    word = "walremnantcanaryword"
    visitor.paste("Secret", f"The {word} is here.")
    reader = connect(settings.db_path)
    reader.execute("BEGIN")
    reader.execute("SELECT COUNT(*) FROM source").fetchone()  # holds a snapshot
    started = time.monotonic()
    deleted = visitor.client.delete(f"/sources/{visitor.sources[0]}", headers=visitor.json_headers())
    assert deleted.status_code == 200
    assert time.monotonic() - started < 5, "a deletion does not hang on another reader"
    writer = connect(settings.db_path)
    try:
        assert Repo(writer).checkpoint(attempts=1) is False, "the reader blocks a complete checkpoint"
        reader.execute("COMMIT")
        purge(settings, Repo(writer))
        wal = settings.db_path.with_name(settings.db_path.name + "-wal")
        data = settings.db_path.read_bytes() + (wal.read_bytes() if wal.exists() else b"")
        assert word.encode() not in data, "the hourly purge completed the erasure"
    finally:
        reader.close()
        writer.close()


def test_sec_04_login_creates_the_notebook_and_a_cross_site_get_writes_nothing(make_visitor, db):
    from tests.conftest import ACCESS_CODE

    visitor = make_visitor(login=False)
    visitor.client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
    count = "SELECT COUNT(*) FROM notebook WHERE kind = 'personal'"
    assert db.execute(count).fetchone()[0] == 1, "the checked login POST created it, not a GET"
    visitor.refresh()
    deleted = visitor.client.delete(f"/notebooks/{visitor.notebook_id}", headers=visitor.json_headers())
    assert deleted.status_code in (200, 303)
    assert db.execute(count).fetchone()[0] == 0
    # Every GET is read-only (re-check RCK-05): with or without fetch metadata, from any origin.
    for headers in (
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-origin"},
        {},
        {"Origin": "https://evil.example"},
    ):
        page = visitor.client.get("/app", headers=headers)
        assert page.status_code == 200 and 'action="/app/continue"' in page.text
        assert db.execute(count).fetchone()[0] == 0, f"a GET wrote ({headers})"
    forged = visitor.client.post("/app/continue", follow_redirects=False)
    assert forged.status_code == 403 and db.execute(count).fetchone()[0] == 0, "no token, no write"
    token = visitor.client.get("/app").text.split('name="csrf_token" value="')[1].split('"')[0]
    done = visitor.client.post("/app/continue", data={"csrf_token": token}, follow_redirects=False)
    assert done.status_code == 303 and db.execute(count).fetchone()[0] == 1


def test_sec_05_the_container_entrypoint_keeps_no_urls_or_addresses(tmp_path):
    """Run uvicorn with the exact arguments of the image's CMD and request a URL carrying a
    canary in its query string: nothing on stdout or stderr may contain it."""
    import json
    import os
    import re
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from pathlib import Path

    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()
    match = re.search(r"^CMD (\[.*?\])\s*$", dockerfile.replace("\\\n", ""), re.M | re.S)
    assert match, "CMD in exec form"
    args = json.loads(match.group(1))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    args = [a if a != "8000" else str(port) for a in args]
    args[args.index("0.0.0.0")] = "127.0.0.1"  # noqa: S104 - replacing the image's bind address
    args[0] = sys.executable
    env = {
        **os.environ,
        "APP_ACCESS_CODE": "entrypoint-test-code",
        "MODEL_PROVIDER": "fake",
        "DATA_DIR": str(tmp_path),
        "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
    }
    server = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        canary = "CANARY_AUDIT_CONTENT_9281"
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/?question={canary}", timeout=2)
                break
            except OSError:
                time.sleep(0.1)
        time.sleep(0.3)
    finally:
        server.terminate()
        output = server.communicate(timeout=10)[0]
    assert "Application startup complete" in output, output[-500:]
    assert canary not in output and "127.0.0.1:" not in output.replace(f"http://127.0.0.1:{port}", "")


def test_sec_05_rejected_requests_log_the_route_not_the_path(visitor, caplog):
    canary = "PATHCANARY1234"
    with caplog.at_level("INFO", logger="controlled_copy"):
        visitor.client.delete(f"/sources/{canary}")  # no CSRF token
    events = " ".join(record.getMessage() for record in caplog.records)
    assert "csrf_rejected" in events and "/sources/{source_id}" in events
    assert canary not in events


def test_sec_05_unexpected_errors_log_the_route_not_the_path(settings, monkeypatch, caplog):
    """Full audit re-check RCK-06: the catch-all 500 handler logged the raw path."""
    from controlled_copy.storage.repo import Repo

    def broken(self, *args, **kwargs):
        raise RuntimeError("simulated defect")

    with TestClient(app_with(settings, FakeProvider()), raise_server_exceptions=False) as client:
        Visitor(client).login()
        monkeypatch.setattr(Repo, "owned_source", broken)
        canary = "URLCANARY-private-words-4711"
        with caplog.at_level("INFO", logger="controlled_copy"):
            response = client.get(f"/sources/{canary}")
    assert response.status_code == 500
    events = " ".join(record.getMessage() for record in caplog.records)
    assert "unhandled_error" in events and "/sources/{source_id}" in events
    assert canary not in events


def test_req_02_the_source_count_is_rechecked_inside_the_write(visitor, services, db):
    """The HTTP preflight refuses a third source at a limit of 2; this checks the guard inside
    the insert transaction, which is what stops two parallel uploads that both passed it."""
    from controlled_copy.storage.repo import CapacityReached, NewSource

    visitor.paste("One", "First text about docks.")
    visitor.paste("Two", "Second text about docks.")
    sid = db.execute("SELECT session_id FROM notebook WHERE id = ?", (visitor.notebook_id,)).fetchone()[0]
    notebook = services.repo.get_notebook(sid, visitor.notebook_id)
    late = NewSource(
        notebook=notebook,
        title="Arrived in parallel",
        kind="paste",
        bytes=10,
        text="Third text.",
        pages=None,
        page_starts=None,
        warnings=[],
        metadata=None,
        metadata_origin="none",
        file_path=None,
        chunks=[],
        vectors=[],
        vector_model="fake",
    )
    with pytest.raises(CapacityReached, match="at most 2 sources"):
        services.repo.insert_source(late, limit=2)
    count = db.execute("SELECT COUNT(*) FROM source WHERE notebook_id = ?", (visitor.notebook_id,))
    assert count.fetchone()[0] == 2
