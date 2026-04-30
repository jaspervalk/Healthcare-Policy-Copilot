"""Document service-level tests for new behavior: dedup + PATCH metadata.

Route-level tests would require TestClient + DB override; these exercise the
service layer directly which is a strict superset of what the routes do.
"""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.errors import DuplicateDocumentError
from app.db import Base
from app.models import Document
from app.services.documents import find_document_by_checksum, update_document_metadata


def _setup_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'docs.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _seed_document(SessionLocal, *, checksum: str = "abc") -> str:
    with SessionLocal() as db:
        document = Document(
            title="Original",
            source_filename="orig.pdf",
            stored_path="/tmp/orig.pdf",
            checksum=checksum,
            ingestion_status="indexed",
            extracted_metadata={},
            page_count=2,
            document_type="policy",
            department="utilization_management",
        )
        db.add(document)
        db.commit()
        return document.id


def test_find_document_by_checksum_returns_existing(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    document_id = _seed_document(SessionLocal, checksum="known-hash")

    with SessionLocal() as db:
        existing = find_document_by_checksum(db, "known-hash")
        assert existing is not None
        assert existing.id == document_id

        missing = find_document_by_checksum(db, "other-hash")
        assert missing is None


def test_update_document_metadata_applies_partial_update(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    document_id = _seed_document(SessionLocal)

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        updated = update_document_metadata(
            db,
            document,
            {"title": "Corrected Title", "policy_status": "draft", "effective_date": date(2026, 1, 1)},
        )
        assert updated.title == "Corrected Title"
        assert updated.policy_status == "draft"
        assert updated.effective_date == date(2026, 1, 1)
        # Untouched fields remain
        assert updated.department == "utilization_management"


def test_update_document_metadata_rejects_non_whitelisted_fields(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    document_id = _seed_document(SessionLocal)

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        with pytest.raises(ValueError, match="not editable"):
            update_document_metadata(db, document, {"checksum": "evil"})


def test_duplicate_document_error_carries_existing_id():
    err = DuplicateDocumentError(existing_document_id="abc-123", title="Foo")
    assert err.existing_document_id == "abc-123"
    assert err.title == "Foo"
