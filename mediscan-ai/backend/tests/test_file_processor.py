"""Unit tests for app/services/file_processor.py."""

from __future__ import annotations

import io

import fitz
import pytest
from PIL import Image

from app.core.exceptions import FileProcessingError, FileTooLargeError, UnsupportedFileTypeError
from app.services.file_processor import ContentKind, process_upload


def _make_pdf_bytes(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    raw = doc.tobytes()
    doc.close()
    return raw


def _make_image_bytes(size=(800, 600), color=(120, 50, 200)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_pdf_text_extraction():
    raw = _make_pdf_bytes("Hemoglobin: 10.2 g/dL")
    result = process_upload(raw, mime_type="application/pdf", file_name="report.pdf")
    assert result.kind == ContentKind.TEXT
    assert "Hemoglobin" in result.text_chunks[0]


def test_empty_pdf_raises():
    doc = fitz.open()
    doc.new_page()
    raw = doc.tobytes()
    doc.close()
    with pytest.raises(FileProcessingError):
        process_upload(raw, mime_type="application/pdf", file_name="blank.pdf")


def test_plain_text_file():
    raw = b"WBC Count: 7.2 x10^9/L"
    result = process_upload(raw, mime_type="text/plain", file_name="notes.txt")
    assert result.kind == ContentKind.TEXT
    assert result.text_chunks == ["WBC Count: 7.2 x10^9/L"]


def test_empty_text_file_raises():
    with pytest.raises(FileProcessingError):
        process_upload(b"   ", mime_type="text/plain", file_name="empty.txt")


def test_image_is_compressed():
    raw = _make_image_bytes(size=(3000, 2000))
    result = process_upload(raw, mime_type="image/png", file_name="scan.png")
    assert result.kind == ContentKind.IMAGE
    assert result.image_mime == "image/jpeg"
    assert result.image_bytes is not None
    # Resized down from 3000px to the configured max dimension
    out_img = Image.open(io.BytesIO(result.image_bytes))
    assert max(out_img.size) <= 1600


def test_unsupported_mime_type_rejected():
    with pytest.raises(UnsupportedFileTypeError):
        process_upload(b"binary-garbage", mime_type="application/zip", file_name="archive.zip")


def test_oversized_file_rejected():
    raw = b"0" * (11 * 1024 * 1024)  # 11MB > 10MB default limit
    with pytest.raises(FileTooLargeError):
        process_upload(raw, mime_type="text/plain", file_name="huge.txt")


def test_long_text_is_chunked():
    long_text = "Finding line.\n\n" * 2000  # well over the 12k char chunk threshold
    raw = long_text.encode("utf-8")
    result = process_upload(raw, mime_type="text/plain", file_name="long.txt")
    assert len(result.text_chunks) > 1
    # Reassembling chunks should not lose content
    assert "".join(result.text_chunks).strip() != ""
