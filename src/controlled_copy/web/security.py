"""Session cookies, CSRF tokens, access-code comparison and security headers."""

from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

SESSION_COOKIE = "cc_session"
CSRF_HEADER = "x-csrf-token"

CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "media-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


def _mac(secret: bytes, purpose: str, value: str) -> str:
    digest = hmac.new(secret, f"{purpose}:{value}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def sign_session(secret: bytes, sid: str) -> str:
    return f"{sid}.{_mac(secret, 'session', sid)}"


def verify_session(secret: bytes, cookie: str | None) -> str | None:
    if not cookie or cookie.count(".") != 1:
        return None
    sid, signature = cookie.split(".", 1)
    if not sid or not hmac.compare_digest(signature.encode(), _mac(secret, "session", sid).encode()):
        return None
    return sid


def csrf_token(secret: bytes, sid: str) -> str:
    return _mac(secret, "csrf", sid)


def csrf_valid(secret: bytes, sid: str, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(str(token).encode(), csrf_token(secret, sid).encode())


def code_matches(given: str, expected: str) -> bool:
    """Constant-time comparison of hashes, so the length of the code does not leak either."""
    return hmac.compare_digest(
        hashlib.sha256(given.encode()).digest(), hashlib.sha256(expected.encode()).digest()
    )


Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class SecurityHeadersMiddleware:
    """Adds security headers to every HTTP response (pure ASGI, no buffering)."""

    def __init__(self, app: ASGIApp, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_static = scope.get("path", "").startswith("/static/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {name.lower() for name, _ in headers}

                def add(name: str, value: str) -> None:
                    if name.encode() not in existing:
                        headers.append((name.encode(), value.encode()))

                add("content-security-policy", CSP)
                add("x-content-type-options", "nosniff")
                add("x-frame-options", "DENY")
                add("referrer-policy", "same-origin")  # "no-referrer" makes browsers send Origin: null
                add("permissions-policy", "camera=(), microphone=(), geolocation=(), payment=()")
                add("cross-origin-opener-policy", "same-origin")
                add("cross-origin-resource-policy", "same-origin")
                # A demo behind an access code: search engines should not list its pages.
                add("x-robots-tag", "noindex, nofollow")
                if is_static:
                    add("cache-control", "public, max-age=31536000, immutable")
                else:
                    add("cache-control", "no-store")
                if self.hsts:
                    add("strict-transport-security", "max-age=31536000")
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
