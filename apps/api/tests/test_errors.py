from app.api.errors import DuplicateDocumentError, map_exception
from app.eval.dataset import DatasetError
from app.services.embeddings import EmbeddingError
from app.services.index_stamp import StampMismatchError
from app.services.upload_safety import FileTooLargeError, InvalidPdfError


def test_map_value_error_is_400():
    http_exc = map_exception(ValueError("bad input"))
    assert http_exc.status_code == 400
    assert http_exc.detail == "bad input"


def test_map_stamp_mismatch_is_409():
    http_exc = map_exception(StampMismatchError("collection mismatch"))
    assert http_exc.status_code == 409


def test_map_duplicate_document_is_409_with_existing_id():
    http_exc = map_exception(DuplicateDocumentError(existing_document_id="doc-123", title="Foo"))
    assert http_exc.status_code == 409
    assert http_exc.detail["existing_document_id"] == "doc-123"
    assert http_exc.detail["title"] == "Foo"


def test_map_file_too_large_is_413():
    http_exc = map_exception(FileTooLargeError(size=200, limit=100))
    assert http_exc.status_code == 413


def test_map_invalid_pdf_is_400():
    http_exc = map_exception(InvalidPdfError("not a pdf"))
    assert http_exc.status_code == 400


def test_map_dataset_error_is_400():
    http_exc = map_exception(DatasetError("missing dataset"))
    assert http_exc.status_code == 400


def test_map_embedding_error_is_502_with_sanitized_detail():
    http_exc = map_exception(EmbeddingError("openai 503: timeout against text-embedding-3-large"))
    assert http_exc.status_code == 502
    # Internal error string must not leak.
    assert "openai" not in http_exc.detail.lower()


def test_map_unknown_exception_is_500_with_sanitized_detail():
    http_exc = map_exception(RuntimeError("some private internal trace"))
    assert http_exc.status_code == 500
    assert "private internal trace" not in http_exc.detail


def test_map_passthrough_existing_http_exception():
    from fastapi import HTTPException

    original = HTTPException(status_code=404, detail="custom")
    mapped = map_exception(original)
    assert mapped is original
