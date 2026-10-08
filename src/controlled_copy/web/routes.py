"""HTTP routes of the core (stage 1).

htmx requests get HTML fragments; `Accept: application/json` gets JSON (used by
the evaluation runner); anything else gets the fragment or a redirect. Every
route that touches visitor data depends on the session, and every route that
changes state also depends on the CSRF check.
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from markupsafe import Markup

from controlled_copy.answering.answer import ask
from controlled_copy.config import Settings
from controlled_copy.errors import UserFacingError
from controlled_copy.ingestion import frontmatter, pipeline
from controlled_copy.ingestion.validate import IngestError
from controlled_copy.limits import DAILY_LIMIT_MESSAGE
from controlled_copy.logs import log_event
from controlled_copy.plugins import StudioAction
from controlled_copy.providers.base import ProviderError
from controlled_copy.purge import remove_uploads
from controlled_copy.services import Services
from controlled_copy.storage.db import connect
from controlled_copy.storage.repo import CapacityReached, OwnedNotebook, sources_full
from controlled_copy.studio.actions import run_overview_template, suggested_questions, suggestions_key
from controlled_copy.studio.engine import core_templates
from controlled_copy.web import views
from controlled_copy.web.deps import (
    ServicesDep,
    SessionDep,
    SettingsDep,
    WriteDep,
    is_htmx,
    json_error,
    same_origin,
    wants_json,
)
from controlled_copy.web.markdown import output_markdown
from controlled_copy.web.security import (
    SESSION_COOKIE,
    code_matches,
    csrf_token,
    sign_session,
    verify_session,
)
from controlled_copy.web.segments import build_segments

router = APIRouter()

DEFAULT_NOTEBOOK_TITLE = "Untitled notebook"
EMBEDDING_UNAVAILABLE = "Indexing failed because the embedding provider is not available. Please try again."


# Rendering helpers -------------------------------------------------------------
def render(
    request: Request,
    name: str,
    context: dict[str, Any],
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        request, name, context, status_code=status, headers=headers
    )


def fragment(request: Request, name: str, context: dict[str, Any]) -> str:
    return request.app.state.templates.get_template(name).render(**context)


def notice(request: Request, message: str, status: int, target: str | None = None) -> Response:
    if wants_json(request):
        return json_error(message, status)
    headers = {"HX-Retarget": target, "HX-Reswap": "innerHTML"} if target and is_htmx(request) else None
    return render(request, "partials/notice.html", {"message": message}, status, headers)


def hx_redirect(request: Request, url: str) -> Response:
    if is_htmx(request):
        return Response(status_code=200, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def json_or_redirect(request: Request, payload: dict[str, Any], url: str, status: int = 200) -> Response:
    return JSONResponse(payload, status_code=status) if wants_json(request) else hx_redirect(request, url)


def landing_page(
    request: Request, settings: Settings, error: str | None = None, status: int = 200
) -> Response:
    return render(
        request, "landing.html", {"retention_days": settings.retention_days, "error": error}, status
    )


def limits_view(settings: Settings) -> dict[str, Any]:
    return {
        "max_sources": settings.max_sources_per_notebook,
        "max_file_mb": settings.max_file_mb,
        "max_pdf_pages": settings.max_pdf_pages,
        "question_chars": settings.max_question_chars,
        "situation_chars": settings.max_situation_chars,
    }


def studio_actions(request: Request) -> list[StudioAction]:
    core = [StudioAction(t.id, t.title, t.description, t.icon) for t in core_templates().values()]
    return core + list(request.app.state.registry.studio_actions)


def _suggestions_state(
    notebook: OwnedNotebook, sources: list[dict[str, Any]], read_only: bool
) -> tuple[bool, list]:
    """(pending, questions): cached questions render at once; otherwise the page loads them."""
    if not sources or read_only:
        return False, []
    if notebook.suggestions_json and notebook.suggestions_key == suggestions_key([s["id"] for s in sources]):
        return False, json.loads(notebook.suggestions_json)
    return True, []


def workspace_context(
    request: Request,
    services: Services,
    notebook: OwnedNotebook,
    initial_viewer: Markup | None = None,
) -> dict[str, Any]:
    repo = services.repo
    sources = [views.source_view(row) for row in repo.list_sources(notebook)]
    read_only = services.budget.read_only()
    settings = services.settings
    notebooks = repo.list_notebooks(services.sid)
    pending, questions = _suggestions_state(notebook, sources, read_only)
    partials = request.app.state.registry.output_partials
    context: dict[str, Any] = {
        "csrf_token": csrf_token(request.app.state.secret, services.sid),
        "notebooks": notebooks,
        "nb": notebook,
        "sources": sources,
        "selected_ids": {s["id"] for s in sources},
        "turns": views.turn_views(repo.list_turns(notebook)),
        "outputs": [
            views.output_view(row, open_=i == 0, partials=partials)
            for i, row in enumerate(repo.list_outputs(notebook))
        ],
        "notice": DAILY_LIMIT_MESSAGE if read_only else None,
        "read_only": read_only,
        "can_create_notebook": sum(n.kind == "personal" for n in notebooks)
        < settings.max_notebooks_per_visitor,
        "limits": limits_view(settings),
        "retention_days": settings.retention_days,
        "ui": {
            "topbar_partials": list(request.app.state.registry.topbar_partials),
            "chat_partials": list(request.app.state.registry.chat_partials),
            "upload_partials": list(request.app.state.registry.upload_partials),
            "studio_actions": studio_actions(request),
        },
        "pending": pending,
        "questions": questions,
        "initial_viewer": initial_viewer,
        "extra": {},
    }
    for hook in request.app.state.registry.view_hooks:
        hook(services, notebook, context)
    return context


def owned_notebook(services: Services, notebook_id: str) -> OwnedNotebook | None:
    return services.repo.get_notebook(services.sid, notebook_id)


def _discard(services: Services, files: list[str]) -> None:
    """After a delete: fold the write-ahead log and remove the uploaded files."""
    services.repo.checkpoint()
    remove_uploads(services.settings, files)


# Public pages ------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
def landing(request: Request, services: ServicesDep) -> Response:
    sid = verify_session(request.app.state.secret, request.cookies.get(SESSION_COOKIE))
    if sid and services.repo.session_last_seen(sid):
        return RedirectResponse("/app", status_code=303)
    return landing_page(request, services.settings)


@router.post("/access", response_class=HTMLResponse)
def access(
    request: Request,
    services: ServicesDep,
    code: Annotated[str, Form(max_length=200)] = "",
) -> Response:
    settings = services.settings
    if not same_origin(request):
        # Login CSRF: another site must not be able to replace a visitor's session.
        return landing_page(request, settings, status=403)
    limiter = request.app.state.access_limiter
    client = request.client.host if request.client else "unknown"
    if limiter.blocked(client):
        log_event("access", outcome="rate_limited")
        return landing_page(request, settings, "Too many attempts. Try again in an hour.", 429)
    expected = settings.app_access_code.get_secret_value() if settings.app_access_code else ""
    if not expected or not code_matches(code, expected):
        limiter.record_failure(client)
        log_event("access", outcome="wrong_code")
        return landing_page(request, settings, "That access code is not valid.", 401)
    existing = verify_session(request.app.state.secret, request.cookies.get(SESSION_COOKIE))
    if existing and services.repo.session_last_seen(existing):
        sid = existing
    else:
        # Every new session costs disk (and, with the governed layer, a seeded copy), so a
        # holder of the access code cannot mint them without limit.
        sessions = request.app.state.session_limiter
        if sessions.blocked(client):
            log_event("access", outcome="session_limited")
            return landing_page(
                request, settings, "Too many new sessions from here. Try again in an hour.", 429
            )
        sessions.record_failure(client)  # counts every new session
        sid = services.repo.create_session()
    log_event("access", outcome="granted", session=sid)
    services.session_id = sid
    _prepare_visitor(request, services)  # first notebook and layer workspaces, on this checked POST
    response = RedirectResponse("/app", status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(request.app.state.secret, sid),
        max_age=settings.retention_hours * 3600,
        httponly=True,
        # Fail secure: Secure in deploy mode and whenever the request came in over HTTPS.
        secure=settings.secure_cookies or request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


@router.get("/video", response_class=HTMLResponse)
def video(request: Request, settings: SettingsDep) -> Response:
    data = None
    if settings.video_mp4:
        data = {"mp4": settings.video_mp4, "vtt": settings.video_vtt, "date": settings.video_date or ""}
    return render(request, "video.html", {"video": data})


@router.get("/healthz")
def healthz(settings: SettingsDep) -> Response:
    """Liveness for the container health check: the process answers and the database opens."""
    try:
        conn = connect(settings.db_path)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return JSONResponse({"status": "database unavailable"}, status_code=503)
    return JSONResponse({"status": "ok"})


# Workspace -----------------------------------------------------------------------
def _prepare_visitor(request: Request, services: Services) -> None:
    """Create what a visitor needs: the layers' workspaces and a first personal notebook."""
    sid = services.sid
    for hook in request.app.state.registry.workspace_hooks:
        hook(services, sid)
    if not any(n.kind == "personal" for n in services.repo.list_notebooks(sid)):
        with contextlib.suppress(CapacityReached):  # a parallel request created it first
            services.repo.create_notebook(sid, DEFAULT_NOTEBOOK_TITLE, limit=1)


@router.get("/app", response_class=HTMLResponse)
def workspace(
    request: Request, services: SessionDep, nb: Annotated[str | None, Query(max_length=64)] = None
) -> Response:
    """Creates and changes nothing, like every GET (a page load only refreshes the session's
    last-seen time): the first notebook is created at the checked login, and a visitor without
    one (after deleting the last) creates it again with the CSRF-checked POST on the continue
    page (full audit SEC-04, re-check RCK-05)."""
    sid = services.sid
    notebooks = services.repo.list_notebooks(sid)
    personal = [n for n in notebooks if n.kind == "personal"]
    if not personal:
        token = csrf_token(request.app.state.secret, sid)
        return render(request, "continue.html", {"csrf_token": token})
    current = next((n for n in notebooks if n.id == nb), personal[0])
    return render(request, "workspace.html", workspace_context(request, services, current))


@router.post("/app/continue")
def continue_to_workspace(request: Request, services: WriteDep) -> Response:
    _prepare_visitor(request, services)
    return RedirectResponse("/app", status_code=303)


@router.post("/notebooks")
def create_notebook(
    request: Request, services: WriteDep, title: Annotated[str, Form(max_length=120)] = ""
) -> Response:
    cleaned = " ".join(title.split()) or DEFAULT_NOTEBOOK_TITLE
    try:
        notebook_id = services.repo.create_notebook(
            services.sid, cleaned, limit=services.settings.max_notebooks_per_visitor
        )
    except CapacityReached as exc:
        return notice(request, exc.message, exc.status, "#toast")
    log_event("notebook_created", session=services.sid, notebook=notebook_id)
    return json_or_redirect(request, {"notebook_id": notebook_id}, f"/app?nb={notebook_id}", 201)


@router.delete("/notebooks/{notebook_id}")
def delete_notebook(request: Request, notebook_id: str, services: WriteDep) -> Response:
    notebook = owned_notebook(services, notebook_id)
    if notebook is None:
        return notice(request, "Notebook not found.", 404, "#toast")
    if notebook.kind != "personal":
        return notice(request, "This workspace cannot be deleted; use Reset instead.", 409, "#toast")
    files = services.repo.delete_notebook(services.sid, notebook_id) or []
    _discard(services, files)
    log_event("notebook_deleted", session=services.sid, notebook=notebook_id, files=len(files))
    return json_or_redirect(request, {"deleted": notebook_id}, "/app")


@router.post("/logout")
def logout(request: Request, services: WriteDep) -> Response:
    """An anonymous session cannot be resumed once its cookie is gone, so logging out deletes
    its notebooks, sources, chats and outputs now instead of after the retention window."""
    files = services.repo.delete_session(services.sid)
    _discard(services, files)
    log_event("logged_out", session=services.sid, files=len(files))
    response = json_or_redirect(request, {"logged_out": True}, "/")
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# Sources -------------------------------------------------------------------------
def _source_list_response(
    request: Request, services: Services, notebook: OwnedNotebook, selected: set[str], new_id: str
) -> Response:
    if wants_json(request):
        return JSONResponse({"source_id": new_id}, status_code=201)
    sources = [views.source_view(row) for row in services.repo.list_sources(notebook)]
    limits = limits_view(services.settings)
    html = fragment(
        request, "partials/source_list.html", {"sources": sources, "selected_ids": selected | {new_id}}
    )
    count = fragment(request, "partials/source_count.html", {"count": len(sources), "limits": limits})
    intro = fragment(
        request,
        "partials/chat_intro.html",
        {"nb": notebook, "sources": sources, "pending": True, "questions": [], "oob": True},
    )
    return HTMLResponse(html + count + intro, status_code=201)


def _extract(
    settings: Settings, file: UploadFile | None, title: str | None, text: str | None
) -> pipeline.Extracted:
    if file is not None and file.filename:
        data = file.file.read(settings.max_file_bytes + 1)
        if len(data) > settings.max_file_bytes:
            raise IngestError(f"The file is larger than {settings.max_file_mb} MB.", 413)
        extracted = pipeline.extract_upload(
            file.filename,
            data,
            max_pages=settings.max_pdf_pages,
            timeout=settings.pdf_parse_timeout_seconds,
            memory_mb=settings.pdf_parse_memory_mb,
            title_limit=settings.max_title_chars,
        )
        extracted.raw = data
        return extracted
    if text is not None:
        if len(text) > settings.max_paste_chars:
            raise IngestError(f"Pasted text is limited to {settings.max_paste_chars:,} characters.", 413)
        return pipeline.extract_paste(title or "Pasted text", text, title_limit=settings.max_title_chars)
    raise IngestError("Choose a file or paste some text.", 422)


@router.post("/notebooks/{notebook_id}/sources")
def add_source(
    request: Request,
    notebook_id: str,
    services: WriteDep,
    file: Annotated[UploadFile | None, File()] = None,
    title: Annotated[str | None, Form(max_length=500)] = None,
    text: Annotated[str | None, Form()] = None,
    source_ids: Annotated[list[str] | None, Form()] = None,
    doc_document_id: Annotated[str | None, Form(max_length=200)] = None,
    doc_revision: Annotated[str | None, Form(max_length=200)] = None,
    doc_status: Annotated[str | None, Form(max_length=200)] = None,
    doc_effective_from: Annotated[str | None, Form(max_length=200)] = None,
    doc_site: Annotated[str | None, Form(max_length=200)] = None,
    doc_roles: Annotated[str | None, Form(max_length=2000)] = None,
) -> Response:
    settings = services.settings
    target = "#add-source-status"
    notebook = owned_notebook(services, notebook_id)
    if notebook is None:
        return notice(request, "Notebook not found.", 404, target)
    if services.repo.count_sources(notebook) >= settings.max_sources_per_notebook:
        full = sources_full(settings.max_sources_per_notebook)  # checked again inside the write
        return notice(request, full.message, full.status, target)
    if services.budget.read_only():
        return notice(request, DAILY_LIMIT_MESSAGE, 503, target)
    try:
        typed = frontmatter.from_form(
            {
                "document_id": doc_document_id,
                "revision": doc_revision,
                "status": doc_status,
                "effective_from": doc_effective_from,
                "site": doc_site,
                "applicable_roles": doc_roles,
            }
        )
    except ValueError as exc:
        return notice(request, str(exc), 422, target)
    try:
        extracted = _extract(settings, file, title, text)
        if typed is not None:
            # Typed metadata replaces the file's own front matter; both are asserted by the uploader.
            extracted.metadata, extracted.metadata_origin = typed, "asserted"
            extracted.warnings = [w for w in extracted.warnings if w != frontmatter.MALFORMED]
        source_id = pipeline.store(services, notebook, extracted, extracted.raw)
    except UserFacingError as exc:
        log_event("source_rejected", session=services.sid, notebook=notebook_id, status=str(exc.status))
        return notice(request, exc.message, exc.status, target)
    except ProviderError:
        return notice(request, EMBEDDING_UNAVAILABLE, 502, target)
    return _source_list_response(request, services, notebook, set(source_ids or []), source_id)


@router.delete("/sources/{source_id}")
def delete_source(request: Request, source_id: str, services: WriteDep) -> Response:
    source = services.repo.owned_source(services.sid, source_id)
    if source is None:
        return notice(request, "Source not found.", 404, "#toast")
    files = services.repo.delete_source(services.sid, source_id) or []
    _discard(services, files)
    log_event("source_deleted", session=services.sid, source=source_id, notebook=source["notebook_id"])
    return json_or_redirect(request, {"deleted": source_id}, f"/app?nb={source['notebook_id']}")


@router.get("/sources/{source_id}", response_class=HTMLResponse)
def view_source(
    request: Request,
    source_id: str,
    services: SessionDep,
    start: Annotated[int | None, Query(ge=0)] = None,
    end: Annotated[int | None, Query(ge=0)] = None,
) -> Response:
    row = services.repo.owned_source(services.sid, source_id, with_text=True)
    if row is None:
        return notice(request, "Source not found.", 404, "#toast")
    text = row["text"]
    highlight = (start, end) if start is not None and end is not None and start < end <= len(text) else None
    page_starts = json.loads(row["page_starts_json"]) if row["page_starts_json"] else None
    source = views.source_view(row)
    focus = None
    if highlight:
        locator = services.repo.locator_at(source_id, highlight[0])
        focus = views.focus_label(row["title"], source["meta"], locator) if locator else None
    context = {
        "s": source,
        "segments": build_segments(text, highlight, page_starts, markdown=row["kind"] == "md"),
        "focus_label": focus,
    }
    for hook in request.app.state.registry.view_hooks:
        hook(services, None, {"viewer": context, "source_row": row})
    html = fragment(request, "partials/viewer.html", context)
    if is_htmx(request):
        return HTMLResponse(html)
    notebook = owned_notebook(services, row["notebook_id"])
    assert notebook is not None  # owned_source already checked the session
    return render(
        request,
        "workspace.html",
        workspace_context(request, services, notebook, initial_viewer=Markup(html)),  # noqa: S704 - autoescaped template output
    )


# Chat ------------------------------------------------------------------------------
@router.post("/notebooks/{notebook_id}/ask")
def ask_question(
    request: Request,
    notebook_id: str,
    services: WriteDep,
    question: Annotated[str, Form(max_length=20000)] = "",
    source_ids: Annotated[list[str] | None, Form()] = None,
) -> Response:
    notebook = owned_notebook(services, notebook_id)
    if notebook is None:
        return notice(request, "Notebook not found.", 404, "#toast")
    try:
        result = ask(services, notebook, question, list(source_ids or []))
    except UserFacingError as exc:
        if wants_json(request):
            return json_error(exc.message, exc.status)
        turn = views.error_turn(question.strip()[: services.settings.max_question_chars], exc.message)
        return render(request, "partials/turn.html", {"t": turn}, exc.status)
    if wants_json(request):
        return JSONResponse(
            {
                "turn_id": result.turn_id,
                "question": result.question,
                "search_query": result.search_query,
                "answer": result.answer,
            }
        )
    turn = views.turn_view(result.turn_id, result.question, result.search_query, result.answer, result.status)
    return render(request, "partials/turn.html", {"t": turn})


@router.post("/notebooks/{notebook_id}/chat/clear")
def clear_chat(request: Request, notebook_id: str, services: WriteDep) -> Response:
    """New chat: the notebook's turns are deleted, so the next question has no earlier context."""
    notebook = owned_notebook(services, notebook_id)
    if notebook is None:
        return notice(request, "Notebook not found.", 404, "#toast")
    removed = services.repo.clear_chat(notebook)
    _discard(services, [])
    log_event("chat_cleared", session=services.sid, notebook=notebook_id, messages=removed)
    return json_or_redirect(request, {"cleared": removed}, f"/app?nb={notebook_id}")


@router.post("/notebooks/{notebook_id}/suggestions", response_class=HTMLResponse)
def suggestions(request: Request, notebook_id: str, services: WriteDep) -> Response:
    """Generating questions calls the model, spends budget and writes the cache: a POST with
    the CSRF check (S-17), never a GET another site could trigger."""
    notebook = owned_notebook(services, notebook_id)
    if notebook is None:
        return HTMLResponse('<div id="suggestions"></div>', status_code=404)
    questions = suggested_questions(services, notebook)
    return render(request, "partials/suggestions.html", {"pending": False, "questions": questions})


# Studio ----------------------------------------------------------------------------
@router.post("/notebooks/{notebook_id}/studio/{template_id}")
def run_studio(
    request: Request,
    notebook_id: str,
    template_id: str,
    services: WriteDep,
    source_ids: Annotated[list[str] | None, Form()] = None,
) -> Response:
    template = core_templates().get(template_id)
    if template is None:
        return notice(request, "Unknown Studio action.", 404, "#studio-status")
    notebook = owned_notebook(services, notebook_id)
    if notebook is None:
        return notice(request, "Notebook not found.", 404, "#studio-status")
    try:
        stored = run_overview_template(services, notebook, template, list(source_ids or []))
    except UserFacingError as exc:
        return notice(request, exc.message, exc.status, "#studio-status")
    if wants_json(request):
        return JSONResponse({"output_id": stored.output_id, "output": stored.output})
    return render_output(request, services, notebook, stored.output_id)


@router.get("/notebooks/{notebook_id}/outputs/{output_id}.md")
def output_as_markdown(
    request: Request,
    notebook_id: str,
    output_id: str,
    services: SessionDep,
    download: Annotated[bool, Query()] = False,
) -> Response:
    """A Studio output as Markdown (copy or download); only from the visitor's own notebook."""
    notebook = owned_notebook(services, notebook_id)
    row = services.repo.get_output(notebook, output_id) if notebook is not None else None
    text = (
        output_markdown(row, request.app.state.registry.output_markdown, core_templates())
        if row is not None
        else None
    )
    if text is None:
        return PlainTextResponse("Not found.", status_code=404)
    headers = {"Cache-Control": "no-store"}
    if download:
        name = re.sub(r"[^a-z0-9-]", "", str(row["template"]).lower()) or "output"
        headers["Content-Disposition"] = f'attachment; filename="{name}-{row["created_at"][:10]}.md"'
    return Response(text, media_type="text/markdown; charset=utf-8", headers=headers)


def render_output(request: Request, services: Services, notebook: OwnedNotebook, output_id: str) -> Response:
    row = services.repo.get_output(notebook, output_id)
    partials = request.app.state.registry.output_partials
    return render(
        request, "partials/output.html", {"o": views.output_view(row, open_=True, partials=partials)}
    )
