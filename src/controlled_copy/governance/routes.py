"""HTTP routes of the governed layer: Resolution Card and workspace Reset."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, Response

from controlled_copy.governance import rules
from controlled_copy.governance.card import CardInput, context_options, run_card
from controlled_copy.governance.seed import reset_workspace
from controlled_copy.logs import log_event
from controlled_copy.studio.actions import StudioError
from controlled_copy.web import views
from controlled_copy.web.deps import WriteDep, wants_json
from controlled_copy.web.routes import hx_redirect, notice, owned_notebook_or_404, render

router = APIRouter()
DEFAULT_ROLE = "warehouse_operator"


def default_context(rows: list, site: str, role: str, as_of: str) -> rules.Context:
    options = context_options(rows)
    chosen_site = (
        site if site in options["sites"] else (options["sites"][0] if options["sites"] else site or "all")
    )
    roles = options["roles"]
    chosen_role = (
        role if role in roles else (DEFAULT_ROLE if DEFAULT_ROLE in roles or not roles else roles[0])
    )
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
    try:
        notebook = owned_notebook_or_404(services, notebook_id)
    except LookupError:
        return notice(request, "Notebook not found.", 404, "#studio-status")
    selected = list(source_ids or [])
    try:
        rows = services.repo.sources_by_ids(notebook, selected)
        context = default_context(rows, site, role, as_of)
        stored = run_card(services, notebook, CardInput(situation, context), selected)
    except StudioError as exc:
        return notice(request, exc.message, exc.status, "#studio-status")
    if wants_json(request):
        return JSONResponse({"output_id": stored.output_id, "output": stored.output})
    row = services.repo.get_output(notebook, stored.output_id)
    partials = request.app.state.registry.output_partials
    return render(
        request, "partials/output.html", {"o": views.output_view(row, open_=True, partials=partials)}
    )


@router.post("/workspace/reset")
def reset(request: Request, services: WriteDep) -> Response:
    sid = services.session_id
    assert sid is not None
    try:
        notebook = reset_workspace(services, sid)
    except Exception as exc:
        log_event("workspace_reset_failed", session=sid, error_type=type(exc).__name__)
        return notice(request, "The workspace could not be reset. Please try again.", 502, "#toast")
    services.repo.checkpoint()
    log_event("workspace_reset", session=sid, notebook=notebook.id)
    if wants_json(request):
        return JSONResponse({"notebook_id": notebook.id})
    return hx_redirect(request, f"/app?nb={notebook.id}")
