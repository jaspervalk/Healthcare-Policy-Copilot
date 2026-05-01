"""End-to-end route tests via FastAPI's TestClient.

Covers the wiring that the service-level tests don't exercise: status-code
mapping, multipart upload, auth gating on PATCH/DELETE, and the dedup 409
contract. Heavy-weight services (Qdrant client, OpenAI calls, BM25 rebuilds,
processed-JSON writes, raw-PDF writes) are stubbed so the suite stays fast and
hermetic.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.documents as documents_module
import app.services.embeddings as embeddings_module
import app.services.query_logs as query_logs_module
from app.core.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Document
from app.services.embeddings import EmbeddingBatch
from app.services.pdf_parser import ParsedDocument, ParsedPage


# A minimal valid-looking PDF: passes the magic-byte check, fails real parsing
# (which we stub anyway).
_PDF_BYTES = b"%PDF-1.4\n%fake\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'routes.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _get_db_override():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db_override
    # query_logs persists on its own session, point that at the test DB too.
    monkeypatch.setattr(query_logs_module, "SessionLocal", TestSessionLocal)

    # Stub the indexing pipeline's external dependencies so the route exercises
    # real wiring without touching Qdrant, OpenAI, the filesystem, or BM25.
    fake_parsed = ParsedDocument(
        title="Stub Document",
        page_count=1,
        pages=[ParsedPage(page_number=1, text="alpha beta gamma delta epsilon")],
        metadata={},
    )
    monkeypatch.setattr(documents_module, "parse_pdf", lambda _path: fake_parsed)

    class _FakeEmbeddingService:
        client = None
        configured_provider = "local-hash"
        configured_model = "md5-bucket"
        local_embedder = embeddings_module.LocalHashingEmbedder(4)

        def embed_many(self, texts):
            return EmbeddingBatch(
                provider="local-hash",
                model="md5-bucket",
                dimensions=4,
                vectors=[[0.1, 0.2, 0.3, 0.4] for _ in texts],
            )

        def embed_query(self, text):
            return self.embed_many([text])

    monkeypatch.setattr(documents_module, "EmbeddingService", _FakeEmbeddingService)

    class _FakeQdrantService:
        collection_name = "policy_chunks"

        def upsert_chunks(self, **_kwargs):
            return None

        def delete_document_chunks(self, _document_id):
            return None

    monkeypatch.setattr(documents_module, "QdrantIndexService", lambda: _FakeQdrantService())
    monkeypatch.setattr(documents_module, "write_bytes", lambda _path, _content: None)
    monkeypatch.setattr(documents_module, "write_json", lambda _path, _payload: None)
    monkeypatch.setattr(documents_module, "delete_path", lambda _path: True)
    monkeypatch.setattr(documents_module, "refresh_hybrid_index", lambda _db: 0)

    # The `_mark_document_failed` helper in the route also calls refresh_hybrid_index;
    # patch it where the route module imports it too.
    import app.api.routes.documents as documents_routes
    monkeypatch.setattr(documents_routes, "refresh_hybrid_index", lambda _db: 0)

    yield TestClient(app)

    app.dependency_overrides.clear()


def _upload(client, content=_PDF_BYTES, filename="policy.pdf"):
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, content, "application/pdf")},
    )


def test_upload_non_pdf_extension_returns_400(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_upload_missing_magic_bytes_returns_400(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("fake.pdf", b"PK\x03\x04 zip dressed as pdf", "application/pdf")},
    )
    assert response.status_code == 400
    assert "%PDF-" in response.json()["detail"]


def test_upload_oversized_file_returns_413(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_bytes", 32)
    huge = _PDF_BYTES + b"x" * 200
    response = _upload(client, content=huge, filename="huge.pdf")
    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]


def test_upload_dedup_returns_409_with_existing_id(client):
    first = _upload(client)
    assert first.status_code == 201, first.text
    document_id = first.json()["document"]["id"]

    second = _upload(client)
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["existing_document_id"] == document_id
    assert detail["title"]


def test_patch_metadata_updates_whitelisted_fields(client):
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]

    response = client.patch(
        f"/api/documents/{document_id}",
        json={"policy_status": "draft", "title": "Operator-Corrected Title"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["policy_status"] == "draft"
    assert body["title"] == "Operator-Corrected Title"


def test_patch_metadata_rejects_empty_body(client):
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]

    response = client.patch(f"/api/documents/{document_id}", json={})
    assert response.status_code == 400


def test_patch_metadata_404_for_missing_document(client):
    response = client.patch(
        "/api/documents/does-not-exist",
        json={"title": "ghost"},
    )
    assert response.status_code == 404


def test_patch_metadata_requires_admin_token_when_set(client, monkeypatch):
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]

    monkeypatch.setattr(settings, "admin_token", "secret-token")

    no_header = client.patch(f"/api/documents/{document_id}", json={"title": "no auth"})
    assert no_header.status_code == 401

    wrong = client.patch(
        f"/api/documents/{document_id}",
        json={"title": "wrong"},
        headers={"Authorization": "Bearer nope"},
    )
    assert wrong.status_code == 401

    right = client.patch(
        f"/api/documents/{document_id}",
        json={"title": "approved"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert right.status_code == 200
    assert right.json()["title"] == "approved"


def test_evals_run_rejects_path_traversal_dataset(client):
    response = client.post(
        "/api/evals/run",
        json={"dataset": "../../etc/passwd"},
    )
    assert response.status_code == 400
    assert "Invalid dataset name" in response.json()["detail"]


def test_evals_run_rejects_unknown_dataset_with_400(client):
    response = client.post(
        "/api/evals/run",
        json={"dataset": "definitely_not_a_real_dataset"},
    )
    assert response.status_code == 400


def test_request_id_header_is_echoed(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


def test_caller_supplied_request_id_is_preserved(client):
    response = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers.get("X-Request-ID") == "abc-123"


def test_mark_document_failed_refreshes_hybrid_index(client, monkeypatch):
    """R2 regression: a failed reindex must clear zombie BM25 entries."""
    refresh_calls: list[int] = []
    import app.api.routes.documents as documents_routes

    monkeypatch.setattr(documents_routes, "refresh_hybrid_index", lambda _db: refresh_calls.append(1) or 0)

    # Successful upload first.
    upload = _upload(client)
    document_id = upload.json()["document"]["id"]
    refresh_calls.clear()

    # Force the reindex to fail by stubbing parse_pdf to raise.
    def _boom(_path):
        raise ValueError("simulated parse failure")

    monkeypatch.setattr(documents_module, "parse_pdf", _boom)

    response = client.post(f"/api/documents/{document_id}/index")
    assert response.status_code == 400

    # Doc should be marked failed AND BM25 should have been refreshed in the
    # mark-failed path. Without R2 the assertion below was 0.
    assert refresh_calls, "refresh_hybrid_index was not called by _mark_document_failed"

    # Confirm the SQL state ended up consistent.
    db_session = next(app.dependency_overrides[get_db]())
    try:
        document = db_session.get(Document, document_id)
        assert document.ingestion_status == "failed"
        assert document.parse_error and "simulated" in document.parse_error
    finally:
        db_session.close()
