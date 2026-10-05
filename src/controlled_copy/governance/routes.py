"""HTTP routes of the governed layer: Resolution Card and workspace Reset."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, Response

from controlled_copy.errors import UserFacingError
from controlled_copy.governance import rules
from controlled_copy.governance.card import CardInput, context_options, run_card
from controlled_copy.governance.seed import reset_workspace
from controlled_copy.logs import log_event
from controlled_copy.studio.actions import StudioError
from controlled_copy.web.deps import WriteDep, wants_json
from controlled_copy.web.routes import json_or_redirect, notice, owned_notebook, render_output

router = APIRouter()
DEFAULT_ROLE = "warehouse_operator"


def _pick(value: str, options: list[str], fallback: str) -> str:
    """The submitted value if the workspace knows it, else the preferred or first option."""
    if value in options:
        return value
    if fallback in options or not options:
        return fallback
    return options[0]


def default_context(rows: list, site: str, role: str, as_of: str) -> rules.Context:
    """The context bar's values, falling back to the workspace's own sites and roles."""
    options = context_options(rows)
    chosen_site = _pick(site, options["sites"], fallback=site or "all")
    chosen_role = _pick(role, options["roles"], fallback=DEFAULT_ROLE)
    try:
        when = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError as exc:
        raise StudioError("Enter the date as YYYY-MM-DD.", 422) from exc
    return rules.Context(site=chosen_site, role=chosen_role, as_of=when)


@router.post("/notebooks/{notebook_id}/studio/resolution-card")
def resolution_card(
    request: Request,
    notebook_id: str,
    services: WriteDep,
    situation: Annotated[str, Form(max_length=20000)] = "",
    site: Annotated[str, Form(max_length=60)] = "",
    role: Annotated[str, Form(max_length=60)] = "",
    as_of: Annotated[str, Form(max_length=10)] = "",
    source_ids: Annotated[list[str] | None, Form()] = None,
) -> Response:
    notebook = owned_notebook(services, notebook_id)
    if notebook is None:
        return notice(request, "Notebook not found.", 404, "#studio-status")
    selected = list(source_ids or [])
    try:
        context = default_context(services.repo.sources_by_ids(notebook, selected), site, role, as_of)
        stored = run_card(services, notebook, CardInput(situation, context), selected)
    except UserFacingError as exc:
        return notice(request, exc.message, exc.status, "#studio-status")
    if wants_json(request):
        return JSONResponse({"output_id": stored.output_id, "output": stored.output})
    return render_output(request, services, notebook, stored.output_id)


@router.post("/workspace/reset")
def reset(request: Request, services: WriteDep) -> Response:
    sid = services.sid
    try:
        notebook = reset_workspace(services, sid)
    except Exception as exc:
        log_event("workspace_reset_failed", session=sid, error_type=type(exc).__name__)
        return notice(request, "The workspace could not be reset. Please try again.", 502, "#toast")
    services.repo.checkpoint()
    log_event("workspace_reset", session=sid, notebook=notebook.id)
    return json_or_redirect(request, {"notebook_id": notebook.id}, f"/app?nb={notebook.id}")
