"""Decide a file's type by its content, not by its name or the browser's MIME type."""

from __future__ import annotations

from pathlib import PurePath

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".txt": "txt", ".md": "md", ".markdown": "md"}


class IngestError(Exception):
    """A user-facing rejection. `message` is safe to show; it never contains file content."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def decode_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestError(
            "This text file is not UTF-8 encoded. Save it as UTF-8 and upload it again.", 415
        ) from exc
    if "\x00" in text:
        raise IngestError("This file looks like binary data, not text.", 415)
    control = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t\f")
    if control > max(8, len(text) // 100):
        raise IngestError("This file looks like binary data, not text.", 415)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def detect_kind(filename: str, data: bytes) -> str:
    """Return 'pdf', 'md' or 'txt', or raise IngestError."""
    if not data.strip():
        raise IngestError("The file is empty.", 422)
    extension = PurePath(filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise IngestError("Unsupported file type. Upload a PDF, TXT or Markdown file.", 415)
    if data.startswith(b"%PDF-"):
        return "pdf"
    if extension == ".pdf":
        raise IngestError("This file is not a valid PDF.", 415)
    return ALLOWED_EXTENSIONS[extension]
