"""Model picker layer (stage 3): each visitor chooses the generation model from a short
allowlist of evaluated models. Loaded only when FEATURE_MODEL_PICKER is on; the core
never imports this package (D-032). The configured fallback model stays automatic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from controlled_copy.config import Settings
from controlled_copy.plugins import Registry
from controlled_copy.services import Services
from controlled_copy.storage.db import Migration

MIGRATIONS = [
    Migration(
        "0201_model_choice",
        """
        CREATE TABLE model_choice (
            session_id TEXT PRIMARY KEY REFERENCES visitor_session(id) ON DELETE CASCADE,
            model TEXT NOT NULL
        )
        """,
    )
]

# Display names for the evaluated models; anything else shows its OpenRouter ID.
LABELS = {
    "openai/gpt-6-luna": "GPT-6 Luna",
    "openai/gpt-6-luna-pro": "GPT-6 Luna Pro",
    "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
}


def label(model: str) -> str:
    return LABELS.get(model, model)


def chosen_model(services: Services) -> str | None:
    """The visitor's stored choice, if it is still on the allowlist."""
    if services.session_id is None:
        return None
    row = services.repo.conn.execute(
        "SELECT model FROM model_choice WHERE session_id = ?", (services.session_id,)
    ).fetchone()
    if row is None or row["model"] not in services.settings.model_choice_list:
        return None
    return str(row["model"])


def _view_hook(services: Services, notebook: Any, context: dict[str, Any]) -> None:
    if "viewer" in context:
        return
    settings = services.settings
    current = chosen_model(services) or settings.model_generation
    context["extra"]["models"] = {
        "choices": [{"id": m, "label": label(m)} for m in settings.model_choice_list],
        "current": current,
    }


def register(registry: Registry, settings: Settings) -> None:
    from controlled_copy.models.routes import router

    registry.migrations.extend(MIGRATIONS)
    registry.routers.append(router)
    registry.template_dirs.append(Path(__file__).parent / "ui")
    registry.topbar_partials.append("models/model_select.html")
    registry.view_hooks.append(_view_hook)
    registry.model_resolvers.append(chosen_model)
