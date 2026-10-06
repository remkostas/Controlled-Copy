"""HTTP routes of the governed layer: Resolution Card and workspace Reset."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, Response

from controlled_copy.errors import UserFacingError
from controlled_copy.governance import rules
from controlled_copy.governance.card import CardInput, context_options, run_card
from controlled_copy.governance.seed import reset_workspace
from controlled_copy.limits import AccessLimiter
from controlled_copy.logs import log_event
from controlled_copy.purge import remove_uploads
from controlled_copy.studio.actions import StudioError
from controlled_copy.web.deps import WriteDep, wants_json
from controlled_copy.web.routes import json_or_redirect, notice, owned_notebook, render_output

router = APIRouter()

RESETS_PER_HOUR = 10  # each Reset rewrites the whole copy; no model calls, but disk and locks


def default_context(rows: list, site: str, role: str, as_of: str) -> rules.Context:
    """The context the visitor chose. A chosen site or role is never replaced, so documents
    for another site or role stay excluded even when none of the selected sources mentions
    the chosen value. A missing site is an error when the documents name sites (guessing one
    would apply another site's instructions); a missing role falls back to the default role."""
    options = context_options(rows)
    if not site:
        if options["sites"]:
            raise StudioError("Choose a site first.", 422)
        site = "all"
    if not role:
        roles = options["roles"]
        role = rules.DEFAULT_ROLE if rules.DEFAULT_ROLE in roles or not roles else roles[0]
    try:
        when = date.fromisoformat(as_of) if as_of else datetime.now(UTC).date()
    except ValueError as exc:
        raise StudioError("Enter the date as YYYY-MM-DD.", 422) from exc
    return rules.Context(site=site, role=role, as_of=when)


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
    rows = services.repo.sources_by_ids(notebook, list(source_ids or []), with_text=True)
    try:
        context = default_context(rows, site.strip(), role.strip(), as_of.strip())
        stored = run_card(services, notebook, CardInput(situation, context), rows)
    except UserFacingError as exc:
        return notice(request, exc.message, exc.status, "#studio-status")
    if wants_json(request):
        return JSONResponse({"output_id": stored.output_id, "output": stored.output})
    return render_output(request, services, notebook, stored.output_id)


@router.post("/workspace/reset")
def reset(request: Request, services: WriteDep) -> Response:
    sid = services.sid
    limiter = getattr(request.app.state, "reset_limiter", None)
    if limiter is None:
        limiter = request.app.state.reset_limiter = AccessLimiter(RESETS_PER_HOUR)
    if limiter.blocked(sid):
        return notice(
            request, "The workspace was reset often in the last hour. Try again later.", 429, "#toast"
        )
    limiter.record_failure(sid)  # counts every attempt
    try:
        notebook, files = reset_workspace(services, sid)
    except UserFacingError as exc:
        return notice(request, exc.message, exc.status, "#toast")
    except Exception as exc:
        log_event("workspace_reset_failed", session=sid, error_type=type(exc).__name__)
        return notice(request, "The workspace could not be reset. Please try again.", 502, "#toast")
    services.repo.checkpoint()
    remove_uploads(services.settings, files)
    log_event("workspace_reset", session=sid, notebook=notebook.id, files=len(files))
    return json_or_redirect(request, {"notebook_id": notebook.id}, f"/app?nb={notebook.id}")
