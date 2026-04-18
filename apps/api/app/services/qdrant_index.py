from __future__ import annotations

from dataclasses import dataclass

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


class QdrantIndexService:
    def __init__(self) -> None:
        if QdrantClient is None or models is None:  # pragma: no cover
            raise RuntimeError("qdrant-client is not installed")

        if settings.qdrant_url:
            self.client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
        else:
            self.client = QdrantClient(path=str(settings.qdrant_local_path))

        self.collection_name = settings.qdrant_collection_name

    def ensure_collection(self, dimensions: int) -> None:
        collection = None
        try:
            collection = self.client.get_collection(self.collection_name)
        except Exception:
            collection = None

        if collection is None:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
            )
            return

        configured = collection.config.params.vectors
        size = getattr(configured, "size", None)
        if size and size != dimensions:
            raise RuntimeError(
                f"Existing Qdrant collection dimension mismatch: expected {dimensions}, found {size}"
            )

    def replace_document_chunks(self, document_id: str, chunks: list[dict], vectors: list[list[float]]) -> None:
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

        self.client.upsert(collection_name=self.collection_name, points=points)

    def delete_document_chunks(self, document_id: str) -> None:
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
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
        self.client.delete(collection_name=self.collection_name, points_selector=selector)

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
        try:
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
        except Exception:
            return []
        return [
            SearchHit(
                chunk_id=str(result.id),
                score=float(result.score),
                payload=result.payload or {},
            )
            for result in results
        ]
