"""Centralized exception → HTTP mapping.

Replaces the ``except Exception → HTTPException(400, str(exc))`` pattern that
conflated user errors with server errors and leaked internal exception strings
in 5xx responses.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.eval.dataset import DatasetError
from app.services.embeddings import EmbeddingError
from app.services.index_stamp import StampMismatchError
from app.services.upload_safety import FileTooLargeError, InvalidPdfError


logger = logging.getLogger(__name__)


class DuplicateDocumentError(Exception):
    """A document with the same checksum already exists."""

    def __init__(self, existing_document_id: str, title: str) -> None:
        super().__init__(f"Document already exists: {existing_document_id}")
        self.existing_document_id = existing_document_id
        self.title = title


def map_exception(exc: Exception) -> HTTPException:
    """Translate internal exception types to HTTPException with appropriate status codes.

    Keep this list explicit — silent generic handling is what made 5xx errors
    look like 4xx in the original code.
    """
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, DuplicateDocumentError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Document with the same content already exists.",
                "existing_document_id": exc.existing_document_id,
                "title": exc.title,
            },
        )
    if isinstance(exc, StampMismatchError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, FileTooLargeError):
        return HTTPException(
            status_code=413,  # Content Too Large; constant name varies across Starlette versions.
            detail=f"File size {exc.size} exceeds the maximum allowed {exc.limit} bytes.",
        )
    if isinstance(exc, InvalidPdfError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, DatasetError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, EmbeddingError):
        # Upstream provider failure: not the caller's fault.
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Embedding provider unavailable. Try again or check provider status.",
        )
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")
    # Unknown: log full trace, return sanitized 500.
    logger.exception("Unhandled exception in route")
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal error. See server logs for details.",
    )
