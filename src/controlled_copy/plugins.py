"""The one registration point for optional layers (D-032).

A layer is a module with `register(registry)`. It is imported by name, and
only when its feature flag is on; the core never imports layer modules. What a
layer can add is exactly what `Registry` lists.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from controlled_copy.config import Settings
from controlled_copy.storage.db import Migration

LAYERS: dict[str, tuple[str, str]] = {
    # name: (module, settings flag)
    "governance": ("controlled_copy.governance", "feature_governance"),
}


@dataclass(frozen=True)
class StudioAction:
    id: str
    title: str
    description: str
    icon: str
    partial: str | None = None


@dataclass
class Registry:
    routers: list[APIRouter] = field(default_factory=list)
    migrations: list[Migration] = field(default_factory=list)
    studio_actions: list[StudioAction] = field(default_factory=list)
    topbar_partials: list[str] = field(default_factory=list)
    template_dirs: list[Path] = field(default_factory=list)
    # Called with (services, session_id) when a visitor opens the workspace.
    workspace_hooks: list[Callable[[Any, str], None]] = field(default_factory=list)
    # Called with (services, notebook_row, context dict) to extend the workspace view.
    view_hooks: list[Callable[[Any, Any, dict[str, Any]], None]] = field(default_factory=list)
    loaded: list[str] = field(default_factory=list)


def load_layers(settings: Settings, registry: Registry) -> Registry:
    for name, (module_name, flag) in LAYERS.items():
        if getattr(settings, flag, False):
            module = importlib.import_module(module_name)
            module.register(registry, settings)
            registry.loaded.append(name)
    return registry
