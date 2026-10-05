"""PDF text extraction in a separate process with a time and memory limit.

A malicious or pathological PDF can make a pure-Python parser loop or allocate
without bound. The parser therefore runs in a child process: if it does not
finish in time it is killed, and an address-space limit stops memory bombs.
Only text is extracted: no rendering, no JavaScript, no embedded files.
This module stays import-light because the child process imports it.
"""

from __future__ import annotations

import io
import multiprocessing
from collections.abc import Callable
from multiprocessing.connection import Connection
from typing import Any

from controlled_copy.ingestion.validate import IngestError

Extractor = Callable[[bytes, int], tuple[str, Any]]


def extract_pages(data: bytes, max_pages: int) -> tuple[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data), strict=False)
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                return "encrypted", None
        except Exception:
            return "encrypted", None
    count = len(reader.pages)
    if count > max_pages:
        return "too_many_pages", count
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "ok", pages


def _child(
    conn: Connection, extractor: Extractor, data: bytes, max_pages: int, memory_mb: int, cpu_seconds: int
) -> None:
    try:
        import resource

        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    except (ImportError, ValueError, OSError):
        pass
    try:
        conn.send(extractor(data, max_pages))
    except MemoryError:
        conn.send(("error", "MemoryError"))
    except RecursionError:
        conn.send(("error", "RecursionError"))
    except Exception as exc:
        conn.send(("error", type(exc).__name__))
    finally:
        conn.close()


def extract_pdf(
    data: bytes,
    *,
    max_pages: int,
    timeout: float,
    memory_mb: int = 1024,
    extractor: Extractor = extract_pages,
) -> list[str]:
    """Return the text of each page, or raise IngestError with a clear message."""
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_child,
        args=(sender, extractor, data, max_pages, memory_mb, int(timeout) + 5),
        daemon=True,
    )
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout):
            raise IngestError(
                f"Reading this PDF took longer than {int(timeout)} seconds, so it was stopped. "
                "The file may be damaged or unusually complex.",
                422,
            )
        try:
            status, payload = receiver.recv()
        except EOFError as exc:
            raise IngestError("This PDF could not be read. The file may be damaged.", 422) from exc
    finally:
        receiver.close()
        if process.is_alive():
            process.kill()
        process.join(timeout=5)
    if status == "ok":
        return list(payload)
    if status == "too_many_pages":
        raise IngestError(f"This PDF has {payload} pages; the limit is {max_pages}.", 413)
    if status == "encrypted":
        raise IngestError("This PDF is password-protected. Remove the password and upload it again.", 422)
    raise IngestError("This PDF could not be read. The file may be damaged.", 422)
