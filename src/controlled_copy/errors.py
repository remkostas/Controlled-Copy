"""Errors whose message is shown to the visitor. Messages never contain document content."""

from __future__ import annotations


class UserFacingError(Exception):
    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


PROVIDER_UNAVAILABLE = "The model provider is not available right now. Please try again in a minute."
