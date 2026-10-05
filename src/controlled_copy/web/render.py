"""Jinja2 environment, static asset URLs and inline SVG icons."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Any

import jinja2
from markupsafe import Markup

WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATE_DIR = WEB_DIR / "templates"


@cache
def asset_version() -> str:
    """Short content hash of the static folder, used to bust browser caches."""
    digest = hashlib.sha256()
    for path in sorted(STATIC_DIR.rglob("*")):
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


@cache
def _icons() -> dict[str, str]:
    icons: dict[str, str] = {}
    for path in (STATIC_DIR / "icons").glob("*.svg"):
        svg = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S).strip()
        svg = re.sub(r'\s+class="[^"]*"', "", svg, count=1)
        svg = re.sub(r'\s+(width|height)="24"', "", svg)
        svg = svg.replace("<svg", '<svg class="icon{extra}" aria-hidden="true" focusable="false"', 1)
        icons[path.stem] = svg
    icons["brand"] = (STATIC_DIR / "brand" / "mark.svg").read_text(encoding="utf-8").strip()
    return icons


def icon(name: str, extra_class: str = "") -> Markup:
    svg = _icons()[name]
    extra = f" {extra_class}" if extra_class and name != "brand" else ""
    return Markup(svg.replace("{extra}", extra))  # noqa: S704 - static, trusted SVG files


def make_environment(
    static_prefix: str = "/static/", extra_dirs: Sequence[Path] = (), **globals_: Any
) -> jinja2.Environment:
    """Core templates first, then layer template folders; `globals_` are available everywhere."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader([TEMPLATE_DIR, *extra_dirs]),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
    )
    version = asset_version()

    def static(path: str) -> str:
        return f"{static_prefix}{path}?v={version}"

    env.globals.update(icon=icon, static=static, **globals_)
    return env
