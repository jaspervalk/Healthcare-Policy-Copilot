import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Chunk, Document
from app.services.embeddings import EmbeddingBatch
from app.services.pdf_parser import ParsedDocument, ParsedPage


def _setup_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'index.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _seed_document(SessionLocal, raw_path):
    raw_path.write_bytes(b"%PDF-stub")
    with SessionLocal() as db:
        document = Document(
            title="Original Title",
            source_filename="original.pdf",
            stored_path=str(raw_path),
            checksum="seed",
            ingestion_status="uploaded",
            extracted_metadata={},
            page_count=0,
        )
        db.add(document)
        db.flush()
        # Pre-existing chunks that a successful reindex would replace.
        db.add(
            Chunk(
                document_id=document.id,
                chunk_index=0,
                section_path="Original",
                page_start=1,
                page_end=1,
                token_count=3,
                text="original chunk",
                normalized_text="original chunk",
                chunk_metadata={},
            )
        )
        db.commit()
        return document.id


def _patch_pipeline(monkeypatch, *, qdrant_service):
    fake_parsed = ParsedDocument(
        title="New Title",
        page_count=1,
        pages=[ParsedPage(page_number=1, text="alpha beta gamma delta")],
        metadata={},
    )

    monkeypatch.setattr("app.services.documents.parse_pdf", lambda _path: fake_parsed)

    class _FakeEmbeddingService:
        def embed_many(self, texts):
            return EmbeddingBatch(
                provider="local-hash",
                model="md5-bucket",
                dimensions=4,
                vectors=[[0.1, 0.2, 0.3, 0.4] for _ in texts],
            )

    monkeypatch.setattr("app.services.documents.EmbeddingService", _FakeEmbeddingService)
    monkeypatch.setattr("app.services.documents.QdrantIndexService", lambda: qdrant_service)
    monkeypatch.setattr("app.services.documents.write_json", lambda *_a, **_kw: None)


def test_index_document_rolls_back_sql_when_qdrant_upsert_fails(tmp_path, monkeypatch):
    SessionLocal = _setup_db(tmp_path)
    document_id = _seed_document(SessionLocal, tmp_path / "doc.pdf")

    class _FailingQdrant:
        collection_name = "policy_chunks"

        def __init__(self):
            self.deleted_for: list[str] = []

        def upsert_chunks(self, **_kwargs):
            raise RuntimeError("qdrant upsert exploded")

        def delete_document_chunks(self, document_id):
            self.deleted_for.append(document_id)

    failing_qdrant = _FailingQdrant()
    _patch_pipeline(monkeypatch, qdrant_service=failing_qdrant)

    from app.services.documents import index_document

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        with pytest.raises(RuntimeError, match="qdrant upsert exploded"):
            index_document(db, document)

    # Fresh session: pre-existing chunk must still be there, document fields unchanged.
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert document.title == "Original Title"
        assert document.ingestion_status == "uploaded"
        chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == document_id)))
        assert len(chunks) == 1
        assert chunks[0].text == "original chunk"

    # Best-effort scrub was attempted.
    assert failing_qdrant.deleted_for == [document_id]


def test_index_document_writes_stamp_on_success(tmp_path, monkeypatch):
    SessionLocal = _setup_db(tmp_path)
    document_id = _seed_document(SessionLocal, tmp_path / "doc.pdf")

    class _OkQdrant:
        collection_name = "policy_chunks"

        def upsert_chunks(self, **_kwargs):
            return None

        def delete_document_chunks(self, _document_id):
            return None

    _patch_pipeline(monkeypatch, qdrant_service=_OkQdrant())

    from app.services.documents import index_document
    from app.services.index_stamp import read_stamp

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        index_document(db, document)

    with SessionLocal() as db:
        stamp = read_stamp(db, "policy_chunks")
        assert stamp is not None
        assert stamp.provider == "local-hash"
        assert stamp.model == "md5-bucket"
        assert stamp.dimensions == 4

        document = db.get(Document, document_id)
        assert document.ingestion_status == "indexed"
        assert document.title == "New Title"


def test_index_document_rejects_stamp_mismatch_before_writing(tmp_path, monkeypatch):
    SessionLocal = _setup_db(tmp_path)
    document_id = _seed_document(SessionLocal, tmp_path / "doc.pdf")

    # Pre-stamp the collection with a *different* embedder.
    from app.services.index_stamp import write_stamp

    with SessionLocal() as db:
        write_stamp(db, name="policy_chunks", provider="openai", model="text-embedding-3-large", dimensions=1024)
        db.commit()

    upserted: list[bool] = []

    class _RecordingQdrant:
        collection_name = "policy_chunks"

        def upsert_chunks(self, **_kwargs):
            upserted.append(True)

        def delete_document_chunks(self, _document_id):
            return None

    _patch_pipeline(monkeypatch, qdrant_service=_RecordingQdrant())

    from app.services.documents import index_document
    from app.services.index_stamp import StampMismatchError

    with SessionLocal() as db:
        document = db.get(Document, document_id)
        with pytest.raises(StampMismatchError):
            index_document(db, document)

    # Stamp validation happens before any Qdrant write.
    assert upserted == []

    # SQL state untouched.
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert document.title == "Original Title"
        assert document.ingestion_status == "uploaded"
