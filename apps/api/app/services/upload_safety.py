from __future__ import annotations

from app.core.config import settings


PDF_MAGIC = b"%PDF-"


class InvalidPdfError(ValueError):
    """Bytes are not a recognizable PDF (magic-byte check failed)."""


class FileTooLargeError(Exception):
    """Upload exceeds max_upload_size_bytes."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"Upload size {size} exceeds limit {limit}")
        self.size = size
        self.limit = limit


def validate_upload(content: bytes) -> None:
    """Raise on size violation or non-PDF content. Caller has already read the bytes."""
    if not content:
        raise ValueError("Uploaded file is empty")
    if len(content) > settings.max_upload_size_bytes:
        raise FileTooLargeError(size=len(content), limit=settings.max_upload_size_bytes)
    if not content.startswith(PDF_MAGIC):
        raise InvalidPdfError("File does not start with the %PDF- header; not a valid PDF.")
