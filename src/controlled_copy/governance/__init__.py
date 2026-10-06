"""Governed-documents layer (stage 2): per-visitor Inbound Operations workspace,
document-control rules and the Resolution Card. Loaded only when FEATURE_GOVERNANCE
is on; the core never imports this package (D-032)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from controlled_copy.config import Settings
from controlled_copy.plugins import Registry, StudioAction
from controlled_copy.services import Services
from controlled_copy.storage.db import Migration

MIGRATIONS = [
    Migration(
        "0101_governance_seed_vectors",
        """
        CREATE TABLE seed_vector (
            corpus_hash TEXT NOT NULL,
            document_key TEXT NOT NULL,
            ordinal INTEGER NOT NULL,
            model TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            PRIMARY KEY (corpus_hash, model, document_key, ordinal)
        )
        """,
    )
]


def _view_hook(services: Services, notebook: Any, context: dict[str, Any]) -> None:
    from controlled_copy.governance.card import context_options, documents_of
    from controlled_copy.governance.rules import DEFAULT_ROLE
    from controlled_copy.governance.seed import WORKSPACE_KIND, scenarios

    if "viewer" in context:
        _superseded_banner(services, context)
        return
    rows = services.repo.list_sources(notebook)
    options = context_options(rows)
    roles = options["roles"]
    context["extra"]["governance"] = {
        "sites": options["sites"],
        "roles": roles,
        "default_role": DEFAULT_ROLE if DEFAULT_ROLE in roles else (roles[0] if roles else ""),
        "today": date.today().isoformat(),
        "scenarios": scenarios() if notebook.kind == WORKSPACE_KIND else [],
        "has_metadata": any(d.origin != "none" for d in documents_of(rows)),
    }


def _superseded_banner(services: Services, context: dict[str, Any]) -> None:
    from controlled_copy.governance.card import documents_of

    viewer, row = context["viewer"], context["source_row"]
    source = viewer["s"]
    if not source.get("meta") or source["meta"].get("status") != "obsolete" or services.session_id is None:
        return
    notebook = services.repo.get_notebook(services.session_id, row["notebook_id"])
    if notebook is None:
        return
    documents = documents_of(services.repo.list_sources(notebook))
    this = next((d for d in documents if d.source_id == row["id"]), None)
    newer = [
        d
        for d in documents
        if this
        and d.id_key
        and d.id_key == this.id_key
        and d.status == "approved"
        and d.revision_key > this.revision_key
    ]
    # A curated revision names the successor; an uploaded claim only when nothing curated
    # does, and then marked as asserted.
    curated = [d for d in newer if d.origin == "curated"]
    if curated:
        source["superseded_by"] = max(curated, key=lambda d: d.revision_key).label
    elif newer:
        source["superseded_by"] = max(newer, key=lambda d: d.revision_key).label + " (asserted by uploader)"


def register(registry: Registry, settings: Settings) -> None:
    from controlled_copy.governance.routes import router
    from controlled_copy.governance.seed import WORKSPACE_KIND, WorkspaceSeeder

    registry.migrations.extend(MIGRATIONS)
    registry.routers.append(router)
    registry.template_dirs.append(Path(__file__).parent / "ui")
    registry.studio_actions.append(
        StudioAction(
            id="resolution-card",
            title="Resolution Card",
            description="What applicable approved instructions require, what is missing, who decides",
            icon="file-search",
            partial="governance/card_form.html",
        )
    )
    registry.topbar_partials.append("governance/reset_button.html")
    registry.output_partials["resolution-card"] = "governance/card_output.html"
    registry.notebook_kinds.append(WORKSPACE_KIND)
    registry.workspace_hooks.append(WorkspaceSeeder())
    registry.view_hooks.append(_view_hook)
