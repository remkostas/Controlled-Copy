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

# Display names for models measured on the evaluation sets; anything else configured in
# MODEL_CHOICES shows its OpenRouter ID.
LABELS = {
    "openai/gpt-6-luna": "GPT-6 Luna",
    "openai/gpt-6-luna-pro": "GPT-6 Luna Pro",
    "openai/gpt-6-sol": "GPT-6 Sol",
    "google/gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
    "google/gemini-3.7-flash": "Gemini 3.7 Flash",
    "anthropic/claude-sonnet-5.5": "Claude Sonnet 5.5",
    "deepseek/deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
    "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
    "x-ai/grok-4.7": "Grok 4.7",
    "moonshotai/kimi-k2.6": "Kimi K2.6",
}
VENDORS = {
    "openai": "OpenAI",
    "google": "Google",
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "x-ai": "xAI",
    "moonshotai": "Moonshot AI",
}


def label(model: str) -> str:
    return LABELS.get(model, model)


def vendor(model: str) -> str:
    prefix = model.split("/", 1)[0]
    return VENDORS.get(prefix, prefix)


def groups(models: list[str]) -> list[dict[str, Any]]:
    """Models grouped by provider, in the configured order (the default model's group first)."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for model in models:
        grouped.setdefault(vendor(model), []).append({"id": model, "label": label(model)})
    return [{"vendor": name, "models": items} for name, items in grouped.items()]


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
        "groups": groups(settings.model_choice_list),
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
