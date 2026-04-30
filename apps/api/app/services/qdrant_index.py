from __future__ import annotations

import threading
from dataclasses import dataclass
from itertools import islice
from typing import Any

from app.core.config import settings

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
except ImportError:  # pragma: no cover
    QdrantClient = None
    models = None


@dataclass
class SearchHit:
    chunk_id: str
    score: float
    payload: dict


# Process-wide singleton. Embedded Qdrant uses a lockfile that does not tolerate
# multiple clients against the same path; constructing one per request was a real
# corruption risk under any concurrency.
_client: Any = None
_client_lock = threading.Lock()


def _build_client() -> Any:
    if QdrantClient is None:  # pragma: no cover
        raise RuntimeError("qdrant-client is not installed")
    if settings.qdrant_url:
        return QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=settings.qdrant_timeout_seconds,
        )
    return QdrantClient(path=str(settings.qdrant_local_path))


def get_qdrant_client() -> Any:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = _build_client()
    return _client


def close_qdrant_client() -> None:
    global _client
    with _client_lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
            _client = None


class QdrantIndexService:
    def __init__(self, client: Any | None = None) -> None:
        if models is None:  # pragma: no cover
            raise RuntimeError("qdrant-client is not installed")
        self.client = client if client is not None else get_qdrant_client()
        self.collection_name = settings.qdrant_collection_name

    @staticmethod
    def _batched(points: list, size: int):
        iterator = iter(points)
        while batch := list(islice(iterator, size)):
            yield batch

    def _ensure_payload_indexes(self) -> None:
        indexed_fields = {
            "document_id": models.PayloadSchemaType.KEYWORD,
            "department": models.PayloadSchemaType.KEYWORD,
            "document_type": models.PayloadSchemaType.KEYWORD,
            "policy_status": models.PayloadSchemaType.KEYWORD,
            "source_filename": models.PayloadSchemaType.KEYWORD,
            "page_start": models.PayloadSchemaType.INTEGER,
            "page_end": models.PayloadSchemaType.INTEGER,
        }

        for field_name, schema in indexed_fields.items():
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema,
                    wait=True,
                )
            except Exception:
                continue

    def collection_exists(self) -> bool:
        try:
            self.client.get_collection(self.collection_name)
            return True
        except Exception:
            return False

    def collection_dimensions(self) -> int | None:
        try:
            collection = self.client.get_collection(self.collection_name)
        except Exception:
            return None
        configured = collection.config.params.vectors
        return getattr(configured, "size", None)

    def ensure_collection(self, dimensions: int) -> bool:
        """Ensure the collection exists at the given dimension. Returns True if created."""
        existing_size = self.collection_dimensions()
        if existing_size is None:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
            )
            self._ensure_payload_indexes()
            return True

        if existing_size != dimensions:
            raise RuntimeError(
                f"Existing Qdrant collection dimension mismatch: expected {dimensions}, found {existing_size}"
            )

        self._ensure_payload_indexes()
        return False

    def upsert_chunks(self, document_id: str, chunks: list[dict], vectors: list[list[float]]) -> None:
        """Delete existing points for this document, then upsert new ones.

        Caller is expected to have already validated the embedding stamp against
        this collection. This method does not validate provider/model — only the
        vector dimension.
        """
        if not chunks:
            return

        self.ensure_collection(len(vectors[0]))
        self.delete_document_chunks(document_id)

        points = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            payload = {
                "chunk_id": chunk["id"],
                "document_id": document_id,
                "document_title": chunk["document_title"],
                "source_filename": chunk["source_filename"],
                "department": chunk["department"],
                "document_type": chunk["document_type"],
                "policy_status": chunk["policy_status"],
                "section_path": chunk["section_path"],
                "page_start": chunk["page_start"],
                "page_end": chunk["page_end"],
                "text": chunk["text"],
                "chunk_metadata": chunk["chunk_metadata"],
            }
            points.append(models.PointStruct(id=chunk["id"], vector=vector, payload=payload))

        for batch in self._batched(points, max(1, settings.qdrant_upsert_batch_size)):
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
                wait=True,
                timeout=settings.qdrant_timeout_seconds,
            )

    # Back-compat alias; kept until callers move over.
    def replace_document_chunks(self, document_id: str, chunks: list[dict], vectors: list[list[float]]) -> None:
        self.upsert_chunks(document_id, chunks, vectors)

    def delete_document_chunks(self, document_id: str) -> None:
        if not self.collection_exists():
            return

        selector = models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            )
        )
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=selector,
            wait=True,
            timeout=settings.qdrant_timeout_seconds,
        )

    def search(self, vector: list[float], limit: int, filters: dict[str, str] | None = None) -> list[SearchHit]:
        filter_conditions = []
        for key, value in (filters or {}).items():
            if value:
                filter_conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )

        query_filter = models.Filter(must=filter_conditions) if filter_conditions else None
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
            results = response.points
        else:  # pragma: no cover
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
        return [
            SearchHit(
                chunk_id=str(result.id),
                score=float(result.score),
                payload=result.payload or {},
            )
            for result in results
        ]
