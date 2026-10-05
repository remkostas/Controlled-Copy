"""The per-request bundle of collaborators that core functions receive."""

from __future__ import annotations

from dataclasses import dataclass

from controlled_copy.config import Settings
from controlled_copy.limits import Budget
from controlled_copy.providers.base import ModelProvider
from controlled_copy.storage.repo import Repo


@dataclass
class Services:
    settings: Settings
    provider: ModelProvider
    repo: Repo
    budget: Budget
    session_id: str | None = None
