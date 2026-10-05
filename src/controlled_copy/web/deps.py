"""Request dependencies: database connection, services, session and CSRF checks."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request

from controlled_copy.config import Settings
from controlled_copy.limits import Budget
from controlled_copy.services import Services
from controlled_copy.storage.db import connect
from controlled_copy.storage.repo import Repo
from controlled_copy.web.security import CSRF_HEADER, SESSION_COOKIE, csrf_valid, verify_session

TOUCH_INTERVAL = timedelta(minutes=1)


class NotAuthenticated(Exception):
    """No valid session: redirect to the landing page."""


class CsrfFailed(Exception):
    """A state-changing request without a valid CSRF token or from a foreign origin."""


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repo(request: Request) -> Iterator[Repo]:
    conn = connect(request.app.state.settings.db_path)
    try:
        yield Repo(conn)
    finally:
        conn.close()


SettingsDep = Annotated[Settings, Depends(get_settings)]
RepoDep = Annotated[Repo, Depends(get_repo)]


def get_services(request: Request, settings: SettingsDep, repo: RepoDep) -> Services:
    return Services(
        settings=settings, provider=request.app.state.provider, repo=repo, budget=Budget(settings, repo)
    )


ServicesDep = Annotated[Services, Depends(get_services)]


def require_session(request: Request, services: ServicesDep) -> Services:
    sid = verify_session(request.app.state.secret, request.cookies.get(SESSION_COOKIE))
    if sid is None:
        raise NotAuthenticated
    last_seen = services.repo.session_last_seen(sid)
    if last_seen is None:
        raise NotAuthenticated
    if datetime.fromisoformat(last_seen) < datetime.now(UTC) - TOUCH_INTERVAL:
        services.repo.touch_session(sid)
    services.session_id = sid
    return services


SessionDep = Annotated[Services, Depends(require_session)]


def same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    host = request.headers.get("host", "")
    return urlsplit(origin).netloc == host


async def require_csrf(request: Request, services: SessionDep) -> Services:
    if not same_origin(request):
        raise CsrfFailed
    token = request.headers.get(CSRF_HEADER)
    if token is None and request.headers.get("content-type", "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        form = await request.form()
        value = form.get("csrf_token")
        token = value if isinstance(value, str) else None
    assert services.session_id is not None
    if not csrf_valid(request.app.state.secret, services.session_id, token):
        raise CsrfFailed
    return services


WriteDep = Annotated[Services, Depends(require_csrf)]


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


def wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "") and not is_htmx(request)
