"""Shared fixtures. Every test uses the fake model provider: no network, no cost."""

from __future__ import annotations

import html
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from controlled_copy.app import create_app
from controlled_copy.config import Settings
from controlled_copy.limits import Budget
from controlled_copy.providers.fake import FakeProvider
from controlled_copy.services import Services
from controlled_copy.storage.db import connect
from controlled_copy.storage.repo import Repo

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "demo-data" / "inbound-operations"
ACCESS_CODE = "test-access-code"
CSRF_RE = re.compile(r'"X-CSRF-Token": "([^"]+)"')
NOTEBOOK_RE = re.compile(r'hx-post="/notebooks/([^/"]+)/ask"')


def corpus_file(name: str) -> bytes:
    return (CORPUS / name).read_bytes()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_access_code=ACCESS_CODE,
        app_secret_key="s" * 48,
        model_provider="fake",
        data_dir=tmp_path / "data",
        evidence_floor=0.05,
        provider_timeout_seconds=5,
        pdf_parse_timeout_seconds=10,
    )


@pytest.fixture
def fake() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def app(settings: Settings, fake: FakeProvider) -> FastAPI:
    return create_app(settings, fake, run_purge=False)


@pytest.fixture
def db(settings: Settings, app: FastAPI) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.db_path)
    yield conn
    conn.close()


@pytest.fixture
def services(settings: Settings, fake: FakeProvider, db: sqlite3.Connection) -> Services:
    repo = Repo(db)
    return Services(settings=settings, provider=fake, repo=repo, budget=Budget(settings, repo))


@dataclass
class Visitor:
    client: TestClient
    csrf: str = ""
    notebook_id: str = ""
    page: str = ""
    sources: list[str] = field(default_factory=list)

    @property
    def headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf}

    def login(self) -> Visitor:
        response = self.client.post("/access", data={"code": ACCESS_CODE}, follow_redirects=False)
        assert response.status_code == 303, response.text
        return self.refresh()

    def refresh(self, notebook_id: str | None = None) -> Visitor:
        url = f"/app?nb={notebook_id}" if notebook_id else "/app"
        response = self.client.get(url)
        assert response.status_code == 200
        self.page = response.text
        self.csrf = html.unescape(CSRF_RE.search(html.unescape(response.text)).group(1))
        self.notebook_id = NOTEBOOK_RE.search(response.text).group(1)
        return self

    def json_headers(self) -> dict[str, str]:
        return {**self.headers, "Accept": "application/json"}

    def upload(self, name: str, data: bytes, notebook_id: str | None = None, expect: int = 201) -> Any:
        response = self.client.post(
            f"/notebooks/{notebook_id or self.notebook_id}/sources",
            files={"file": (name, data, "application/octet-stream")},
            headers=self.json_headers(),
        )
        assert response.status_code == expect, response.text
        if expect == 201:
            self.sources.append(response.json()["source_id"])
        return response

    def paste(self, title: str, text: str, notebook_id: str | None = None, expect: int = 201) -> Any:
        response = self.client.post(
            f"/notebooks/{notebook_id or self.notebook_id}/sources",
            data={"title": title, "text": text},
            headers=self.json_headers(),
        )
        assert response.status_code == expect, response.text
        if expect == 201:
            self.sources.append(response.json()["source_id"])
        return response

    def ask(self, question: str, source_ids: list[str] | None = None, notebook_id: str | None = None) -> Any:
        return self.client.post(
            f"/notebooks/{notebook_id or self.notebook_id}/ask",
            data={"question": question, "source_ids": source_ids if source_ids is not None else self.sources},
            headers=self.json_headers(),
        )

    def briefing(self, source_ids: list[str] | None = None) -> Any:
        return self.client.post(
            f"/notebooks/{self.notebook_id}/studio/briefing",
            data={"source_ids": source_ids if source_ids is not None else self.sources},
            headers=self.json_headers(),
        )


@pytest.fixture
def make_visitor(app: FastAPI) -> Iterator[Any]:
    clients: list[TestClient] = []

    def factory(login: bool = True) -> Visitor:
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        visitor = Visitor(client)
        return visitor.login() if login else visitor

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def visitor(make_visitor: Any) -> Visitor:
    return make_visitor()
