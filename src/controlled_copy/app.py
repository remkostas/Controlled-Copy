"""Application factory.

`create_app()` checks the configuration, applies migrations (core first, then
those of enabled layers), wires the model provider, middleware, routes and the
hourly purge, and loads optional layers through the registry.
Run with: uvicorn controlled_copy.app:app (or `fastapi run`).
"""

from __future__ import annotations

import secrets
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import jinja2
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.templating import Jinja2Templates

from controlled_copy.config import Settings
from controlled_copy.limits import AccessLimiter
from controlled_copy.logs import configure_logging, log_event
from controlled_copy.plugins import Registry, load_layers
from controlled_copy.providers.base import ModelProvider
from controlled_copy.providers.fake import FakeProvider
from controlled_copy.providers.openrouter import OpenRouterProvider
from controlled_copy.purge import purge
from controlled_copy.storage.db import CORE_MIGRATIONS, apply_migrations, connect
from controlled_copy.storage.repo import Repo
from controlled_copy.web.deps import CsrfFailed, NotAuthenticated, is_htmx, wants_json
from controlled_copy.web.render import STATIC_DIR, TEMPLATE_DIR, make_environment
from controlled_copy.web.routes import router
from controlled_copy.web.security import SecurityHeadersMiddleware

BODY_OVERHEAD = 1024 * 1024
BODY_TOO_LARGE = "controlled_copy.body_too_large"
TOO_LARGE_MESSAGE = "The request is too large. Files may be up to {mb} MB."


class BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Rejects request bodies above the limit before the app parses them."""

    def __init__(self, app: Any, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        length = headers.get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.limit:
            await self._reject(send)
            return
        received = 0
        started = False

        async def limited_receive() -> Any:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit:
                    # FastAPI wraps body-parsing errors in a 400; the flag lets the handler answer 413.
                    scope[BODY_TOO_LARGE] = True
                    raise BodyTooLarge
            return message

        async def tracking_send(message: Any) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLarge:
            if not started:
                await self._reject(send)

    async def _reject(self, send: Any) -> None:
        body = b"The request is too large."
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def build_provider(settings: Settings) -> ModelProvider:
    if settings.model_provider == "fake":
        return FakeProvider()
    assert settings.openrouter_api_key is not None
    return OpenRouterProvider(
        settings.openrouter_api_key.get_secret_value(),
        settings.openrouter_base_url,
        settings.provider_timeout_seconds,
    )


def _purge_loop(app: FastAPI, stop: threading.Event) -> None:
    settings: Settings = app.state.settings
    while True:
        try:
            conn = connect(settings.db_path)
            try:
                purge(settings, Repo(conn))
            finally:
                conn.close()
        except Exception as exc:
            log_event("purge_failed", error_type=type(exc).__name__)
        if stop.wait(settings.purge_interval_seconds):
            return


def create_app(
    settings: Settings | None = None, provider: ModelProvider | None = None, run_purge: bool = True
) -> FastAPI:
    settings = settings or Settings()
    settings.check_startup()
    configure_logging(settings.app_debug)

    registry = load_layers(settings, Registry())
    settings.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    try:
        apply_migrations(conn, CORE_MIGRATIONS + registry.migrations)
    finally:
        conn.close()

    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        thread = None
        if run_purge:
            thread = threading.Thread(target=_purge_loop, args=(app, stop), daemon=True, name="purge")
            thread.start()
        yield
        stop.set()
        if thread is not None:
            thread.join(timeout=5)
        close = getattr(app.state.provider, "close", None)
        if callable(close):
            close()

    app = FastAPI(
        title=settings.product_name,
        debug=settings.app_debug,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.provider = provider or build_provider(settings)
    app.state.registry = registry
    app.state.access_limiter = AccessLimiter(settings.access_attempts_per_hour)
    secret = (
        settings.app_secret_key.get_secret_value() if settings.app_secret_key else secrets.token_urlsafe(32)
    )
    app.state.secret = secret.encode()

    env = make_environment()
    if registry.template_dirs:
        env.loader = jinja2.ChoiceLoader(
            [
                jinja2.FileSystemLoader(TEMPLATE_DIR),
                *(jinja2.FileSystemLoader(d) for d in registry.template_dirs),
            ]
        )
    app.state.templates = Jinja2Templates(env=env)

    # Added last = outermost: every response, including a 413 from the size guard, gets the headers.
    app.add_middleware(BodySizeLimitMiddleware, limit=settings.max_file_bytes + BODY_OVERHEAD)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.secure_cookies)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(router)
    for layer_router in registry.routers:
        app.include_router(layer_router)

    @app.exception_handler(NotAuthenticated)
    async def not_authenticated(request: Request, exc: NotAuthenticated) -> Response:
        if is_htmx(request):
            return Response(status_code=401, headers={"HX-Redirect": "/"})
        if wants_json(request) or request.method not in ("GET", "HEAD"):
            return JSONResponse(
                {"error": "Session missing or expired. Enter the access code again."}, status_code=401
            )
        return RedirectResponse("/", status_code=303)

    @app.exception_handler(CsrfFailed)
    async def csrf_failed(request: Request, exc: CsrfFailed) -> Response:
        log_event("csrf_rejected", path=request.url.path, method=request.method)
        return JSONResponse(
            {"error": "The request could not be verified. Reload the page and try again."}, status_code=403
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> Response:
        # The default handler echoes the submitted values; never send content back or log it.
        log_event("invalid_request", path=request.url.path, method=request.method, errors=len(exc.errors()))
        return JSONResponse({"error": "The request was not valid."}, status_code=422)

    too_large = TOO_LARGE_MESSAGE.format(mb=settings.max_file_bytes // (1024 * 1024))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        status = 413 if request.scope.get(BODY_TOO_LARGE) else exc.status_code
        message = {404: "Not found.", 405: "Method not allowed.", 413: too_large}.get(
            status, "The request failed."
        )
        if wants_json(request) or is_htmx(request) or request.url.path.startswith("/static/"):
            return JSONResponse({"error": message}, status_code=status)
        page = f'<!doctype html><title>{status}</title><p>{message} <a href="/">Start page</a></p>'
        return HTMLResponse(page, status_code=status)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> Response:
        log_event(
            "unhandled_error", path=request.url.path, method=request.method, error_type=type(exc).__name__
        )
        return HTMLResponse(
            "<!doctype html><title>Error</title><p>Something went wrong. Please try again.</p>",
            status_code=500,
        )

    log_event(
        "app_started", mode=settings.app_mode.value, kind=settings.model_provider, layers=len(registry.loaded)
    )
    return app


def __getattr__(name: str) -> Any:
    # `uvicorn controlled_copy.app:app` builds the app lazily from the environment.
    if name == "app":
        return create_app()
    raise AttributeError(name)
