"""From an upload or pasted text to a stored, indexed source.

1. Check type by content and size (validate.py); nothing is stored on rejection.
2. Extract text: PDF per page in a time-limited subprocess; Markdown and text as is;
   front matter parsed into document metadata.
3. Flag pages with little or no text.
4. Chunk with exact character offsets.
5. Embed every chunk (batched) through the provider; each batch is one model call.
6. Store file, source, chunks, vectors and full-text rows in one transaction.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Any

from controlled_copy.ingestion import chunking
from controlled_copy.ingestion.frontmatter import split_front_matter
from controlled_copy.ingestion.pdf import extract_pdf
from controlled_copy.ingestion.validate import IngestError, decode_text, detect_kind
from controlled_copy.logs import log_event
from controlled_copy.providers.base import ProviderError, call_with_deadline
from controlled_copy.services import Services
from controlled_copy.storage.repo import ChunkRecord, NewSource

MIN_PAGE_CHARS = 20
KIND_EXTENSION = {"pdf": ".pdf", "md": ".md", "txt": ".txt"}


@dataclass
class Extracted:
    kind: str
    title: str
    text: str
    bytes: int
    chunks: list[chunking.Chunk]
    pages: int | None = None
    page_starts: list[int] | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] | None = None
    metadata_origin: str = "none"


def _clean_title(title: str, limit: int) -> str:
    cleaned = " ".join(title.split())
    return cleaned[:limit] or "Untitled source"


def extract_upload(
    filename: str, data: bytes, *, max_pages: int, timeout: float, memory_mb: int, title_limit: int
) -> Extracted:
    kind = detect_kind(filename, data)
    stem = _clean_title(PurePath(filename or "source").stem.replace("_", " "), title_limit)
    if kind == "pdf":
        pages = extract_pdf(data, max_pages=max_pages, timeout=timeout, memory_mb=memory_mb)
        text, starts = chunking.join_pages(pages)
        empty = sum(1 for page in pages if len("".join(page.split())) < MIN_PAGE_CHARS)
        warnings = []
        if empty:
            noun = "page" if empty == 1 else "pages"
            warnings.append(f"{empty} {noun} without extractable text")
        chunks = chunking.chunk_pdf(text, starts)
        result = Extracted("pdf", stem, text, len(data), chunks, len(pages), starts, warnings)
    else:
        decoded = decode_text(data)
        if kind == "md":
            metadata, body, warning = split_front_matter(decoded)
            chunks = chunking.chunk_markdown(body)
            title = (
                _clean_title(metadata["title"], title_limit) if metadata and metadata.get("title") else stem
            )
            result = Extracted(
                "md",
                title,
                body,
                len(data),
                chunks,
                warnings=[warning] if warning else [],
                metadata=metadata,
                metadata_origin="asserted" if metadata else "none",
            )
        else:
            result = Extracted("txt", stem, decoded, len(data), chunking.chunk_plain(decoded))
    if not result.chunks:
        raise IngestError(
            "No text could be extracted from this file. Scanned PDFs need OCR, which this demo does not do.",
            422,
        )
    return result


def extract_paste(title: str, text: str, *, title_limit: int) -> Extracted:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    if not cleaned.strip():
        raise IngestError("The pasted text is empty.", 422)
    chunks = chunking.chunk_plain(cleaned)
    return Extracted("paste", _clean_title(title, title_limit), cleaned, len(cleaned.encode()), chunks)


def embedding_input(title: str, chunk: chunking.Chunk) -> str:
    """Contextual header: the title and section help retrieval for short chunks."""
    return f"{title}\n{chunk.locator}\n{chunk.text}"


def embed_texts(services: Services, texts: list[str], kind: str = "embed") -> list[list[float]]:
    settings = services.settings
    batch = max(1, settings.embedding_batch_size)
    batches = [texts[i : i + batch] for i in range(0, len(texts), batch)]
    services.budget.check(services.session_id, calls=len(batches))
    vectors: list[list[float]] = []
    for part in batches:
        services.budget.consume(services.session_id, kind)
        result = call_with_deadline(
            lambda part=part: services.provider.embed(part, model=settings.model_embedding),
            settings.provider_timeout_seconds,
        )
        if len(result.vectors) != len(part):
            raise ProviderError("embedding count mismatch")
        vectors.extend(result.vectors)
    return vectors


def store(services: Services, notebook_id: str, extracted: Extracted, raw: bytes | None) -> str:
    started = time.monotonic()
    vectors = embed_texts(services, [embedding_input(extracted.title, c) for c in extracted.chunks])
    file_name: str | None = None
    uploads = services.settings.uploads_dir
    if raw is not None:
        uploads.mkdir(parents=True, exist_ok=True)
        file_name = secrets.token_hex(16) + KIND_EXTENSION.get(extracted.kind, ".bin")
        (uploads / file_name).write_bytes(raw)
    try:
        source_id = services.repo.insert_source(
            NewSource(
                notebook_id=notebook_id,
                title=extracted.title,
                kind=extracted.kind,
                bytes=extracted.bytes,
                text=extracted.text,
                pages=extracted.pages,
                page_starts=extracted.page_starts,
                warnings=extracted.warnings,
                metadata=extracted.metadata,
                metadata_origin=extracted.metadata_origin,
                file_path=file_name,
                chunks=[
                    ChunkRecord(c.ordinal, c.locator, c.page, c.char_start, c.char_end, c.text)
                    for c in extracted.chunks
                ],
                vectors=vectors,
                vector_model=services.settings.model_embedding,
            )
        )
    except BaseException:
        if file_name:
            (uploads / file_name).unlink(missing_ok=True)
        raise
    log_event(
        "source_ingested",
        session=services.session_id,
        notebook=notebook_id,
        source=source_id,
        kind=extracted.kind,
        bytes=extracted.bytes,
        pages=extracted.pages,
        chunks=len(extracted.chunks),
        warnings=len(extracted.warnings),
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return source_id
