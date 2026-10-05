"""Stage 2 fixtures: the same app with the governed layer switched on."""

from __future__ import annotations

import html
import re
from typing import Any

import pytest

from controlled_copy.config import Settings

OPS_RE = re.compile(r'<option value="([^"]+)"[^>]*>\s*Inbound Operations')
SOURCE_RE = re.compile(r'name="source_ids" value="([^"]+)"')


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"feature_governance": True})


class Workspace:
    def __init__(self, visitor: Any) -> None:
        self.visitor = visitor
        self.refresh()

    def refresh(self) -> None:
        page = self.visitor.client.get("/app").text
        self.id = OPS_RE.search(page).group(1)
        self.page = self.visitor.client.get(f"/app?nb={self.id}").text
        self.source_ids = SOURCE_RE.findall(self.page)

    def card(self, situation: str, *, site: str = "HAM-01", role: str = "warehouse_operator", as_of: str = "2026-10-07", source_ids: list[str] | None = None, htmx: bool = False) -> Any:
        headers = {**self.visitor.headers, **({"HX-Request": "true"} if htmx else {"Accept": "application/json"})}
        return self.visitor.client.post(
            f"/notebooks/{self.id}/studio/resolution-card",
            data={"situation": situation, "site": site, "role": role, "as_of": as_of, "source_ids": source_ids if source_ids is not None else self.source_ids},
            headers=headers,
        )

    def source_titles(self) -> list[str]:
        return [html.unescape(t) for t in re.findall(r'class="source__title"[^>]*>.*?<span>([^<]+)</span>', self.page, re.S)]


@pytest.fixture
def workspace(visitor: Any) -> Workspace:
    return Workspace(visitor)
