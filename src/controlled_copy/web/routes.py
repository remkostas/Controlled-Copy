"""HTTP routes of the core (stage 1).

htmx requests get HTML fragments; `Accept: application/json` gets JSON (used by
the evaluation runner); anything else gets the fragment or a redirect. Every
route that touches visitor data depends on the session, and every route that
changes state also depends on the CSRF check.
"""

from __future__ import annotations

import contextlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from markupsafe import Markup

from controlled_copy.answering.answer import AskError, ask
from controlled_copy.ingestion import pipeline
from controlled_copy.ingestion.validate import IngestError
from controlled_copy.limits import DAILY_LIMIT_MESSAGE, LimitExceeded
from controlled_copy.logs import log_event
from controlled_copy.providers.base import ProviderError
from controlled_copy.services import Services
from controlled_copy.storage.repo import CapacityReached, OwnedNotebook
from controlled_copy.studio.actions import StudioError, run_overview_template, suggested_questions
from controlled_copy.studio.engine import core_templates
from controlled_copy.web import views
from controlled_copy.web.deps import (
    ServicesDep,
    SessionDep,
    SettingsDep,
    WriteDep,
    is_htmx,
    same_origin,
    wants_json,
)
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


# Rendering helpers -------------------------------------------------------------
def render(
    request: Request,
    name: str,
    context: dict[str, Any],
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    settings = request.app.state.settings
    base = {"product_name": settings.product_name, "tagline": settings.product_tagline}
    return request.app.state.templates.TemplateResponse(
        request, name, {**base, **context}, status_code=status, headers=headers
    )


def fragment(request: Request, name: str, context: dict[str, Any]) -> str:
    template = request.app.state.templates.get_template(name)
    settings = request.app.state.settings
    return template.render(product_name=settings.product_name, tagline=settings.product_tagline, **context)


def notice(
    request: Request, message: str, status: int, target: str | None = None, kind: str = "error"
) -> Response:
    if wants_json(request):
        return JSONResponse({"error": message}, status_code=status)
    headers = {"HX-Retarget": target, "HX-Reswap": "innerHTML"} if target and is_htmx(request) else None
    return render(request, "partials/notice.html", {"message": message, "kind": kind}, status, headers)


def hx_redirect(request: Request, url: str) -> Response:
    if is_htmx(request):
        return Response(status_code=200, headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


def limits_view(settings: Any) -> dict[str, Any]:
    return {
        "max_sources": settings.max_sources_per_notebook,
        "max_file_mb": settings.max_file_bytes // (1024 * 1024),
        "max_pdf_pages": settings.max_pdf_pages,
        "question_chars": settings.max_question_chars,
        "situation_chars": settings.max_situation_chars,
    }


def studio_actions(request: Request) -> list[dict[str, Any]]:
    actions = [
        {"id": t.id, "title": t.title, "description": t.description, "icon": t.icon, "partial": None}
        for t in core_templates().values()
    ]
    actions += [vars(a) for a in request.app.state.registry.studio_actions]
    return actions


def workspace_context(
    request: Request,
    services: Services,
    notebook: Any,
    selected_ids: set[str] | None = None,
    initial_viewer: Markup | None = None,
) -> dict[str, Any]:
    repo = services.repo
    assert services.session_id is not None
    sources = [views.source_view(row) for row in repo.list_sources(notebook)]
    selected = {s["id"] for s in sources} if selected_ids is None else selected_ids
    read_only = services.budget.read_only()
    settings = services.settings
    context: dict[str, Any] = {
        "csrf_token": csrf_token(request.app.state.secret, services.session_id),
        "notebooks": [
            {"id": n["id"], "title": n["title"], "kind": n["kind"]}
            for n in repo.list_notebooks(services.session_id)
        ],
        "nb": {"id": notebook["id"], "title": notebook["title"], "kind": notebook["kind"]},
        "sources": sources,
        "selected_ids": selected,
        "turns": views.turn_views(repo.list_messages(notebook)),
        "outputs": [
            views.output_view(row, open_=i == 0) for i, row in enumerate(repo.list_outputs(notebook))
        ],
        "notice": DAILY_LIMIT_MESSAGE if read_only else None,
        "read_only": read_only,
        "can_create_notebook": repo.count_notebooks(services.session_id) < settings.max_notebooks_per_visitor,
        "limits": limits_view(settings),
        "ui": {
            "topbar_partials": list(request.app.state.registry.topbar_partials),
            "studio_actions": studio_actions(request),
        },
        "pending": bool(sources) and not read_only,
        "questions": [],
        "initial_viewer": initial_viewer,
        "extra": {},
    }
    for hook in request.app.state.registry.view_hooks:
        hook(services, notebook, context)
    return context


def owned_notebook_or_404(services: Services, notebook_id: str) -> OwnedNotebook:
    assert services.session_id is not None
    notebook = services.repo.get_notebook(services.session_id, notebook_id)
    if notebook is None:
        raise LookupError
    return notebook


# Public pages ------------------------------------------------------------------
@router.get("/", response_class=HTMLResponse)
def landing(request: Request, services: ServicesDep) -> Response:
    sid = verify_session(request.app.state.secret, request.cookies.get(SESSION_COOKIE))
    if sid and services.repo.session_last_seen(sid):
        return RedirectResponse("/app", status_code=303)
    return render(
        request, "landing.html", {"retention_days": services.settings.retention_hours // 24, "error": None}
    )


@router.post("/access", response_class=HTMLResponse)
def access(
    request: Request,
    services: ServicesDep,
    code: Annotated[str, Form(max_length=200)] = "",
) -> Response:
    settings = services.settings
    if not same_origin(request):
        # Login CSRF: another site must not be able to replace a visitor's session.
        return render(
            request, "landing.html", {"retention_days": settings.retention_hours // 24, "error": None}, 403
        )
    limiter = request.app.state.access_limiter
    client = request.client.host if request.client else "unknown"
    context = {"retention_days": settings.retention_hours // 24}
    if limiter.blocked(client):
        log_event("access", outcome="rate_limited")
        return render(
            request, "landing.html", {**context, "error": "Too many attempts. Try again in an hour."}, 429
        )
    expected = settings.app_access_code.get_secret_value() if settings.app_access_code else ""
    if not expected or not code_matches(code, expected):
        limiter.record_failure(client)
        log_event("access", outcome="wrong_code")
        return render(request, "landing.html", {**context, "error": "That access code is not valid."}, 401)
    existing = verify_session(request.app.state.secret, request.cookies.get(SESSION_COOKIE))
    sid = (
        existing if existing and services.repo.session_last_seen(existing) else services.repo.create_session()
    )
    log_event("access", outcome="granted", session=sid)
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
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Workspace -----------------------------------------------------------------------
@router.get("/app", response_class=HTMLResponse)
def workspace(
    request: Request, services: SessionDep, nb: Annotated[str | None, Query(max_length=64)] = None
) -> Response:
    sid = services.session_id
    assert sid is not None
    for hook in request.app.state.registry.workspace_hooks:
        hook(services, sid)
    notebooks = services.repo.list_notebooks(sid)
    if not notebooks:
        with contextlib.suppress(CapacityReached):  # a parallel request created it first
            services.repo.create_notebook(sid, DEFAULT_NOTEBOOK_TITLE, limit=1)
        notebooks = services.repo.list_notebooks(sid)
    current = next((n for n in notebooks if n["id"] == nb), None)
    if current is None:
        personal = [n for n in notebooks if n["kind"] == "personal"]
        current = personal[0] if personal else notebooks[0]
    return render(request, "workspace.html", workspace_context(request, services, current))


@router.post("/notebooks")
def create_notebook(
    request: Request, services: WriteDep, title: Annotated[str, Form(max_length=120)] = ""
) -> Response:
    sid = services.session_id
    assert sid is not None
    limit = services.settings.max_notebooks_per_visitor
    if services.repo.count_notebooks(sid) >= limit:
        return notice(
            request, f"You can have at most {limit} notebooks. Delete one to create another.", 409, "#toast"
        )
    cleaned = " ".join(title.split()) or DEFAULT_NOTEBOOK_TITLE
    try:
        notebook_id = services.repo.create_notebook(sid, cleaned, limit=limit)
    except CapacityReached:
        return notice(
            request, f"You can have at most {limit} notebooks. Delete one to create another.", 409, "#toast"
        )
    log_event("notebook_created", session=sid, notebook=notebook_id)
    if wants_json(request):
        return JSONResponse({"notebook_id": notebook_id}, status_code=201)
    return hx_redirect(request, f"/app?nb={notebook_id}")


@router.delete("/notebooks/{notebook_id}")
def delete_notebook(request: Request, notebook_id: str, services: WriteDep) -> Response:
    sid = services.session_id
    assert sid is not None
    notebook = services.repo.get_notebook(sid, notebook_id)
    if notebook is None:
        return notice(request, "Notebook not found.", 404, "#toast")
    if notebook["kind"] != "personal":
        return notice(request, "This workspace cannot be deleted; use Reset instead.", 409, "#toast")
    files = services.repo.delete_notebook(sid, notebook_id) or []
    services.repo.checkpoint()
    for name in files:
        (services.settings.uploads_dir / name).unlink(missing_ok=True)
    log_event("notebook_deleted", session=sid, notebook=notebook_id, files=len(files))
    if wants_json(request):
        return JSONResponse({"deleted": notebook_id})
    return hx_redirect(request, "/app")


# Sources -------------------------------------------------------------------------
def _source_list_response(
    request: Request, services: Services, notebook: OwnedNotebook, selected: set[str], new_id: str
) -> Response:
    if wants_json(request):
        return JSONResponse({"source_id": new_id}, status_code=201)
    sources = [views.source_view(row) for row in services.repo.list_sources(notebook)]
    html = fragment(
        request, "partials/source_list.html", {"sources": sources, "selected_ids": selected | {new_id}}
    )
    count = fragment(
        request,
        "partials/source_count.html",
        {"count": len(sources), "limits": limits_view(services.settings)},
    )
    intro = fragment(
        request,
        "partials/chat_intro.html",
        {"nb": dict(notebook), "sources": sources, "pending": True, "questions": [], "oob": True},
    )
    return HTMLResponse(html + count + intro, status_code=201)


@router.post("/notebooks/{notebook_id}/sources")
def add_source(
    request: Request,
    notebook_id: str,
    services: WriteDep,
    file: Annotated[UploadFile | None, File()] = None,
    title: Annotated[str | None, Form(max_length=500)] = None,
    text: Annotated[str | None, Form()] = None,
    source_ids: Annotated[list[str] | None, Form()] = None,
) -> Response:
    settings = services.settings
    target = "#add-source-status"
    try:
        notebook = owned_notebook_or_404(services, notebook_id)
    except LookupError:
        return notice(request, "Notebook not found.", 404, target)
    if services.repo.count_sources(notebook) >= settings.max_sources_per_notebook:
        return notice(
            request, f"A notebook holds at most {settings.max_sources_per_notebook} sources.", 409, target
        )
    if services.budget.read_only():
        return notice(request, DAILY_LIMIT_MESSAGE, 503, target)
    try:
        if file is not None and file.filename:
            data = file.file.read(settings.max_file_bytes + 1)
            if len(data) > settings.max_file_bytes:
                raise IngestError(
                    f"The file is larger than {settings.max_file_bytes // (1024 * 1024)} MB.", 413
                )
            extracted = pipeline.extract_upload(
                file.filename,
                data,
                max_pages=settings.max_pdf_pages,
                timeout=settings.pdf_parse_timeout_seconds,
                memory_mb=settings.pdf_parse_memory_mb,
                title_limit=settings.max_title_chars,
            )
            raw: bytes | None = data
        elif text is not None:
            if len(text) > settings.max_paste_chars:
                raise IngestError(f"Pasted text is limited to {settings.max_paste_chars:,} characters.", 413)
            extracted = pipeline.extract_paste(
                title or "Pasted text", text, title_limit=settings.max_title_chars
            )
            raw = None
        else:
            raise IngestError("Choose a file or paste some text.", 422)
        source_id = pipeline.store(services, notebook, extracted, raw)
    except IngestError as exc:
        log_event(
            "source_rejected", session=services.session_id, notebook=notebook_id, status=str(exc.status)
        )
        return notice(request, exc.message, exc.status, target)
    except LimitExceeded as exc:
        return notice(request, exc.message, exc.status, target)
    except CapacityReached:
        return notice(
            request, f"A notebook holds at most {settings.max_sources_per_notebook} sources.", 409, target
        )
    except ProviderError:
        return notice(
            request,
            "Indexing failed because the embedding provider is not available. Please try again.",
            502,
            target,
        )
    selected = set(source_ids or [])
    return _source_list_response(request, services, notebook, selected, source_id)


@router.delete("/sources/{source_id}")
def delete_source(request: Request, source_id: str, services: WriteDep) -> Response:
    sid = services.session_id
    assert sid is not None
    source = services.repo.owned_source(sid, source_id)
    if source is None:
        return notice(request, "Source not found.", 404, "#toast")
    files = services.repo.delete_source(sid, source_id) or []
    services.repo.checkpoint()
    for name in files:
        (services.settings.uploads_dir / name).unlink(missing_ok=True)
    log_event("source_deleted", session=sid, source=source_id, notebook=source["notebook_id"])
    if wants_json(request):
        return JSONResponse({"deleted": source_id})
    return hx_redirect(request, f"/app?nb={source['notebook_id']}")


@router.get("/sources/{source_id}", response_class=HTMLResponse)
def view_source(
    request: Request,
    source_id: str,
    services: SessionDep,
    start: Annotated[int | None, Query(ge=0)] = None,
    end: Annotated[int | None, Query(ge=0)] = None,
) -> Response:
    sid = services.session_id
    assert sid is not None
    row = services.repo.owned_source(sid, source_id)
    if row is None:
        return notice(request, "Source not found.", 404, "#toast")
    text = row["text"]
    highlight = (start, end) if start is not None and end is not None and start < end <= len(text) else None
    page_starts = json.loads(row["page_starts_json"]) if row["page_starts_json"] else None
    source = views.source_view(row)
    chunks = services.repo.chunks_for_sources([source_id])
    focus = (
        views.focus_label_for(chunks, highlight[0], row["title"], source["metadata"]) if highlight else None
    )
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
    notebook = services.repo.get_notebook(sid, row["notebook_id"])
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
    try:
        notebook = owned_notebook_or_404(services, notebook_id)
    except LookupError:
        return notice(request, "Notebook not found.", 404, "#toast")
    try:
        result = ask(services, notebook, question, list(source_ids or []))
    except AskError as exc:
        if wants_json(request):
            return JSONResponse({"error": exc.message}, status_code=exc.status)
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
    turn = views.turn_view(result.turn_id, result.question, result.search_query, result.answer)
    return render(request, "partials/turn.html", {"t": turn})


@router.get("/notebooks/{notebook_id}/suggestions", response_class=HTMLResponse)
def suggestions(request: Request, notebook_id: str, services: SessionDep) -> Response:
    try:
        notebook = owned_notebook_or_404(services, notebook_id)
    except LookupError:
        return HTMLResponse('<div id="suggestions"></div>', status_code=404)
    questions = suggested_questions(services, notebook)
    return render(
        request,
        "partials/suggestions.html",
        {"pending": False, "questions": questions, "nb": {"id": notebook_id}},
    )


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
    try:
        notebook = owned_notebook_or_404(services, notebook_id)
        stored = run_overview_template(services, notebook, template, list(source_ids or []))
    except LookupError:
        return notice(request, "Notebook not found.", 404, "#studio-status")
    except StudioError as exc:
        return notice(request, exc.message, exc.status, "#studio-status")
    if wants_json(request):
        return JSONResponse({"output_id": stored.output_id, "output": stored.output})
    row = services.repo.get_output(notebook, stored.output_id)
    return render(request, "partials/output.html", {"o": views.output_view(row, open_=True)})
