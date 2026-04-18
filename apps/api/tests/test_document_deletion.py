from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Chunk, Document
from app.services.documents import delete_document


def test_delete_document_removes_database_row_and_local_artifacts(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'delete-test.db'}", future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    raw_path = tmp_path / "policy.pdf"
    raw_path.write_bytes(b"fake-pdf")
    processed_path = tmp_path / "policy.json"
    processed_path.write_text("{}", encoding="utf-8")
    deleted_ids: list[str] = []

    class FakeQdrantIndexService:
        def delete_document_chunks(self, document_id: str) -> None:
            deleted_ids.append(document_id)

    monkeypatch.setattr("app.services.documents.QdrantIndexService", FakeQdrantIndexService)
    monkeypatch.setattr("app.services.documents.processed_document_path", lambda document_id: processed_path)

    with SessionLocal() as db:
        document = Document(
            title="Policy Manual",
            source_filename="policy.pdf",
            stored_path=str(raw_path),
            checksum="checksum",
            ingestion_status="indexed",
            extracted_metadata={},
            page_count=3,
        )
        db.add(document)
        db.flush()
        db.add(
            Chunk(
                document_id=document.id,
                chunk_index=0,
                section_path="1. Scope",
                page_start=1,
                page_end=1,
                token_count=12,
                text="Policy text",
                normalized_text="policy text",
                chunk_metadata={},
            )
        )
        db.commit()
        db.refresh(document)

        result = delete_document(db, document)

        assert result.document_id == document.id
        assert result.deleted_chunk_count == 1
        assert result.removed_from_index is True
        assert result.raw_file_deleted is True
        assert result.processed_artifact_deleted is True
        assert deleted_ids == [document.id]
        assert db.get(Document, document.id) is None
        assert not Path(raw_path).exists()
        assert not Path(processed_path).exists()
