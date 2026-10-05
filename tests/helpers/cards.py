"""Scripted fake-model responses for Resolution Card tests (stage 2)."""

from __future__ import annotations

from controlled_copy.providers.fake import FakeRequest, default_responder


def card_responder(build):
    """Use `build(request)` for Resolution Card calls, the default responder otherwise."""

    def responder(request: FakeRequest):
        if request.schema_name == "resolution_card":
            return build(request)
        return default_responder(request)

    return responder


def passage_with(request: FakeRequest, needle: str) -> tuple[str, str]:
    for pid, text in request.passages():
        if needle.lower() in text.lower():
            start = text.lower().index(needle.lower())
            return pid, text[start : start + len(needle)]
    raise AssertionError(f"no passage contains {needle!r}")


def empty_card(**sections):
    base = {"required_actions": [], "missing_information": [], "escalation": [], "conflicts": []}
    base.update(sections)
    return base
