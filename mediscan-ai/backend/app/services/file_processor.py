"""
File ingestion: PDF/image/text -> either extracted text (cheap, no LLM call)
or a compressed image payload (sent to a vision-capable model).

Why this matters for token budget: PyMuPDF extracts PDF text locally, for
free, with zero network calls. Only images go to the vision API, and even
those are downscaled/recompressed first via Pillow to stay well under
provider upload limits and minimize tokens billed against the free quota.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from enum import Enum

import fitz  # PyMuPDF
from PIL import Image

from app.core.config import get_settings
from app.core.exceptions import FileProcessingError, FileTooLargeError, UnsupportedFileTypeError
from app.core.logging import get_logger

logger = get_logger(__name__)

# Rough chars-per-token heuristic for English text (~4 chars/token). Used only
# to decide when to chunk — not billed precision, just a practical threshold.
CHARS_PER_CHUNK = 12_000


class ContentKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"


@dataclass
class ProcessedFile:
    kind: ContentKind
    text_chunks: list[str]
    image_bytes: bytes | None
    image_mime: str | None
    original_mime: str
    file_name: str


def _extract_pdf_text(raw: bytes) -> str:
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises a generic RuntimeError on bad PDFs
        raise FileProcessingError(f"Could not open PDF: {exc}") from exc

    pages: list[str] = []
    try:
        for page in doc:
            pages.append(page.get_text())
    finally:
        doc.close()

    text = "\n".join(pages).strip()
    if not text:
        raise FileProcessingError(
            "No extractable text found in PDF. It may be a scanned image-only PDF — "
            "try uploading it as an image instead so vision analysis can run."
        )
    return text


def _compress_image(raw: bytes) -> tuple[bytes, str]:
    settings = get_settings()
    try:
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
    except Exception as exc:
        raise FileProcessingError(f"Could not read image: {exc}") from exc

    max_dim = settings.image_compress_max_dimension
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    target_bytes = settings.image_compress_target_kb * 1024
    quality = 90
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)

    while buf.tell() > target_bytes and quality > 30:
        quality -= 10
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)

    logger.info(
        "image_compressed",
        extra={"final_quality": quality, "final_size_kb": buf.tell() // 1024},
    )
    return buf.getvalue(), "image/jpeg"


def _chunk_text(text: str) -> list[str]:
    if len(text) <= CHARS_PER_CHUNK:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHARS_PER_CHUNK, len(text))
        # Try to break on a paragraph boundary near the end of the window
        boundary = text.rfind("\n\n", start, end)
        if boundary == -1 or boundary <= start:
            boundary = end
        chunks.append(text[start:boundary])
        start = boundary
    return chunks


def process_upload(raw: bytes, *, mime_type: str, file_name: str) -> ProcessedFile:
    """Routes raw upload bytes to the appropriate extraction path."""
    settings = get_settings()

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(raw) > max_bytes:
        raise FileTooLargeError(
            f"File exceeds {settings.max_upload_size_mb}MB limit.",
            details={"size_bytes": len(raw)},
        )

    if mime_type not in settings.allowed_mime_types:
        raise UnsupportedFileTypeError(
            f"Unsupported file type: {mime_type}",
            details={"allowed": settings.allowed_mime_types},
        )

    if mime_type == "application/pdf":
        text = _extract_pdf_text(raw)
        return ProcessedFile(
            kind=ContentKind.TEXT,
            text_chunks=_chunk_text(text),
            image_bytes=None,
            image_mime=None,
            original_mime=mime_type,
            file_name=file_name,
        )

    if mime_type == "text/plain":
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            raise FileProcessingError("Text file is empty.")
        return ProcessedFile(
            kind=ContentKind.TEXT,
            text_chunks=_chunk_text(text),
            image_bytes=None,
            image_mime=None,
            original_mime=mime_type,
            file_name=file_name,
        )

    if mime_type.startswith("image/"):
        compressed, out_mime = _compress_image(raw)
        return ProcessedFile(
            kind=ContentKind.IMAGE,
            text_chunks=[],
            image_bytes=compressed,
            image_mime=out_mime,
            original_mime=mime_type,
            file_name=file_name,
        )

    # Unreachable given the allow-list check above, but keeps mypy/readers honest.
    raise UnsupportedFileTypeError(f"Unhandled mime type: {mime_type}")
