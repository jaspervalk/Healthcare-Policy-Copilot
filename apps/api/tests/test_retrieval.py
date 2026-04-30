import pytest

import app.services.hybrid_index as hybrid_module
import app.services.retrieval as retrieval_module
from app.schemas import QueryFilters
from app.services.embeddings import EmbeddingBatch
from app.services.qdrant_index import SearchHit


class _StubEmbedding:
    def __init__(self) -> None:
        self.local_embedder = None
        self.client = None

    def embed_query(self, _text):
        return EmbeddingBatch(
            provider="local-hash", model="md5-bucket", dimensions=4, vectors=[[0.1, 0.2, 0.3, 0.4]]
        )


class _StubQdrant:
    collection_name = "policy_chunks"

    def __init__(self, hits) -> None:
        self._hits = hits

        class _Client:
            def retrieve(self, *_a, **_kw):
                return []

        self.client = _Client()

    def search(self, vector, limit, filters=None):
        return self._hits[:limit]


class _StubHybrid:
    ready = True

    def __init__(self, sparse_hits) -> None:
        self._sparse = sparse_hits

    def search(self, _query, limit):
        return self._sparse[:limit]


def _hit(chunk_id, score, source_filename="a.pdf"):
    return SearchHit(
        chunk_id=chunk_id,
        score=score,
        payload={
            "document_id": f"doc-{source_filename}",
            "document_title": source_filename,
            "source_filename": source_filename,
            "section_path": None,
            "page_start": 1,
            "page_end": 1,
            "text": f"text-{chunk_id}",
            "chunk_metadata": {},
            "policy_status": "active",
        },
    )


@pytest.fixture(autouse=True)
def _reset_hybrid_singleton():
    hybrid_module.reset_hybrid_index()
    yield
    hybrid_module.reset_hybrid_index()


def test_dense_mode_returns_qdrant_hits_only(monkeypatch):
    dense_hits = [_hit("c1", 0.9), _hit("c2", 0.5)]
    monkeypatch.setattr(retrieval_module, "EmbeddingService", _StubEmbedding)
    monkeypatch.setattr(retrieval_module, "QdrantIndexService", lambda: _StubQdrant(dense_hits))

    service = retrieval_module.RetrievalService()
    provider, results = service.search("hello", top_k=2, mode="dense")

    assert provider == "local-hash"
    assert [r.chunk_id for r in results] == ["c1", "c2"]
    assert results[0].score == 0.9


def test_hybrid_mode_fuses_dense_and_sparse(monkeypatch):
    dense_hits = [_hit("c1", 0.9), _hit("c2", 0.5), _hit("c3", 0.3)]
    sparse_hits = [("c3", 12.0), ("c1", 8.0)]

    monkeypatch.setattr(retrieval_module, "EmbeddingService", _StubEmbedding)
    monkeypatch.setattr(retrieval_module, "QdrantIndexService", lambda: _StubQdrant(dense_hits))
    monkeypatch.setattr(retrieval_module, "get_hybrid_index", lambda: _StubHybrid(sparse_hits))

    service = retrieval_module.RetrievalService()
    _, results = service.search("hello", top_k=3, mode="hybrid")

    chunk_ids = [r.chunk_id for r in results]
    # c3 was top sparse and present dense -> RRF should beat c2 which was only in dense.
    assert chunk_ids.index("c3") < chunk_ids.index("c2")


def test_hybrid_mode_falls_back_to_dense_when_sparse_index_empty(monkeypatch):
    dense_hits = [_hit("c1", 0.9), _hit("c2", 0.5)]

    class _EmptySparse:
        ready = False

        def search(self, *_a, **_kw):
            return []

    monkeypatch.setattr(retrieval_module, "EmbeddingService", _StubEmbedding)
    monkeypatch.setattr(retrieval_module, "QdrantIndexService", lambda: _StubQdrant(dense_hits))
    monkeypatch.setattr(retrieval_module, "get_hybrid_index", lambda: _EmptySparse())

    service = retrieval_module.RetrievalService()
    _, results = service.search("hello", top_k=2, mode="hybrid")

    assert [r.chunk_id for r in results] == ["c1", "c2"]


def test_hybrid_mode_drops_sparse_only_chunks_when_filtering(monkeypatch):
    """Sparse index doesn't know about filters; sparse-only candidates must be dropped
    when the caller passed a filter, otherwise filtered queries become unfiltered."""
    dense_hits = [_hit("c1", 0.9, source_filename="a.pdf")]
    sparse_hits = [("c1", 5.0), ("c99", 12.0)]  # c99 not in dense -> would bypass filter.

    monkeypatch.setattr(retrieval_module, "EmbeddingService", _StubEmbedding)
    monkeypatch.setattr(retrieval_module, "QdrantIndexService", lambda: _StubQdrant(dense_hits))
    monkeypatch.setattr(retrieval_module, "get_hybrid_index", lambda: _StubHybrid(sparse_hits))

    service = retrieval_module.RetrievalService()
    _, results = service.search(
        "hello",
        top_k=5,
        filters=QueryFilters(department="utilization_management"),
        mode="hybrid",
    )

    assert [r.chunk_id for r in results] == ["c1"]
