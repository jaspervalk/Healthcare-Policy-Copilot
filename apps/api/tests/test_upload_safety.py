import pytest

from app.core.config import settings
from app.services.upload_safety import FileTooLargeError, InvalidPdfError, validate_upload


def test_validate_upload_accepts_pdf_magic():
    validate_upload(b"%PDF-1.7\nrest of file")


def test_validate_upload_rejects_empty():
    with pytest.raises(ValueError):
        validate_upload(b"")


def test_validate_upload_rejects_non_pdf_magic():
    with pytest.raises(InvalidPdfError):
        validate_upload(b"PK\x03\x04 zip file")


def test_validate_upload_rejects_too_large(monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_bytes", 10)
    with pytest.raises(FileTooLargeError):
        validate_upload(b"%PDF-" + b"x" * 100)
