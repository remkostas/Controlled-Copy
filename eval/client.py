"""Drive the app over HTTP in-process with the real model provider (evaluation only)."""

from __future__ import annotations

import hashlib
import html
import json
import re
import secrets
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from pydantic import SecretStr

from controlled_copy.app import create_app
from controlled_copy.config import AppMode, Settings

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval"


def provenance(case_file: Path) -> dict[str, Any]:
    """Which code and which cases produced a result: the commit, whether tracked files had
    uncommitted changes, and a hash of the case file. Written into every result file."""

    def git(*args: str) -> str:
        try:
            done = subprocess.run(  # noqa: S603 - fixed git arguments, no shell
                ["git", *args],  # noqa: S607 - git from PATH
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return done.stdout.strip()

    return {
        "commit": git("rev-parse", "HEAD") or "unknown",
        "dirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "cases_sha256": hashlib.sha256(case_file.read_bytes()).hexdigest()[:16],
    }


def provenance_line(info: dict[str, Any]) -> str:
    dirty = ", with uncommitted changes" if info["dirty"] else ""
    return f"Code `{info['commit'][:10]}`{dirty}; case file sha256 `{info['cases_sha256']}`."


CACHE = EVAL / ".cache"
CSRF_RE = re.compile(r'"X-CSRF-Token": "([^"]+)"')
NOTEBOOK_RE = re.compile(r'hx-post="/notebooks/([^/"]+)/ask"')
SOURCE_ID_RE = re.compile(r'name="source_ids" value="([^"]+)"')
DOC_TEXT_RE = re.compile(r'<div class="doc-text">(.*?)</div>\s*</div>', re.S)
PAGE_LABEL_RE = re.compile(r'<span class="page-break">[^<]*</span>')


def fetch_document(key: str) -> tuple[str, bytes]:
    sources = json.loads((EVAL / "sources.json").read_text())
    meta = sources[key]
    CACHE.mkdir(exist_ok=True)
    path = CACHE / meta["file_name"]
    if not path.exists():
        request = urllib.request.Request(meta["url"], headers={"User-Agent": "Mozilla/5.0 (evaluation)"})
        with urllib.request.urlopen(request, timeout=60) as response, path.open("wb") as out:
            shutil.copyfileobj(response, out)
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != meta["sha256"]:
        raise RuntimeError(f"{path.name}: SHA-256 mismatch ({digest})")
    return meta["file_name"], data


def eval_settings(**overrides: Any) -> Settings:
    base = Settings(_env_file=ROOT / ".env")
    update = {
        "app_mode": AppMode.LOCAL,
        "app_access_code": SecretStr(secrets.token_urlsafe(12)),
        "app_secret_key": SecretStr(secrets.token_urlsafe(40)),
        "data_dir": Path(tempfile.mkdtemp(prefix="cc-eval-")),
        "model_calls_per_visitor_hour": 10_000,
        "model_calls_per_day": 100_000,
        "resets_per_visitor_hour": 10_000,  # one Reset per case
    }
    update.update(overrides)
    return base.model_copy(update=update)


class AppClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.app = create_app(settings, run_purge=False)
        self.client = TestClient(self.app)
        self.client.__enter__()
        code = settings.app_access_code.get_secret_value() if settings.app_access_code else ""
        response = self.client.post("/access", data={"code": code}, follow_redirects=False)
        assert response.status_code == 303, response.status_code
        page = self.client.get("/app").text
        self.csrf = html.unescape(CSRF_RE.search(html.unescape(page)).group(1))
        self.first_notebook = NOTEBOOK_RE.search(page).group(1)

    def close(self) -> None:
        self.client.__exit__(None, None, None)
        shutil.rmtree(self.settings.data_dir, ignore_errors=True)

    @property
    def headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf, "Accept": "application/json"}

    def new_notebook(self, title: str) -> str:
        response = self.client.post("/notebooks", data={"title": title}, headers=self.headers)
        response.raise_for_status()
        return response.json()["notebook_id"]

    def delete_notebook(self, notebook_id: str) -> None:
        self.client.delete(f"/notebooks/{notebook_id}", headers=self.headers).raise_for_status()

    def upload(self, notebook_id: str, name: str, data: bytes) -> str:
        response = self.client.post(
            f"/notebooks/{notebook_id}/sources", files={"file": (name, data)}, headers=self.headers
        )
        if response.status_code != 201:
            raise RuntimeError(f"upload {name}: {response.status_code} {response.text[:200]}")
        return response.json()["source_id"]

    def ask(self, notebook_id: str, question: str, source_ids: list[str]) -> tuple[int, dict[str, Any]]:
        response = self.client.post(
            f"/notebooks/{notebook_id}/ask",
            data={"question": question, "source_ids": source_ids},
            headers=self.headers,
        )
        return response.status_code, response.json()

    def studio(self, notebook_id: str, template: str, source_ids: list[str]) -> tuple[int, dict[str, Any]]:
        response = self.client.post(
            f"/notebooks/{notebook_id}/studio/{template}",
            data={"source_ids": source_ids},
            headers=self.headers,
        )
        return response.status_code, response.json()

    def reset_workspace(self) -> tuple[str, list[str]]:
        """A fresh copy of the curated workspace (governed layer): its notebook and source IDs."""
        response = self.client.post("/workspace/reset", headers=self.headers)
        response.raise_for_status()
        notebook_id = response.json()["notebook_id"]
        page = self.client.get(f"/app?nb={notebook_id}").text
        return notebook_id, SOURCE_ID_RE.findall(page)

    def card(
        self, notebook_id: str, situation: str, source_ids: list[str], context: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        response = self.client.post(
            f"/notebooks/{notebook_id}/studio/resolution-card",
            data={"situation": situation, "source_ids": source_ids, **context},
            headers=self.headers,
        )
        return response.status_code, response.json()

    def source_text(self, source_id: str) -> str:
        """The extracted text exactly as the viewer shows it (page labels removed)."""
        body = self.client.get(f"/sources/{source_id}", headers={"HX-Request": "true"}).text
        inner = DOC_TEXT_RE.search(body).group(1)
        inner = PAGE_LABEL_RE.sub("", inner)
        return html.unescape(re.sub(r"<[^>]+>", "", inner))
