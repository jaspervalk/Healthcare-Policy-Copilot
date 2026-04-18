from __future__ import annotations

from app.schemas import QueryChunkResult, QueryFilters
from app.services.embeddings import EmbeddingService
from app.services.qdrant_index import QdrantIndexService


class RetrievalService:
    def __init__(self) -> None:
        self.embedding_service = EmbeddingService()
        self.index_service = QdrantIndexService()

    def search(self, question: str, top_k: int, filters: QueryFilters | None = None) -> tuple[str, list[QueryChunkResult]]:
        batch = self.embedding_service.embed_query(question)
        query_vector = batch.vectors[0]
        filter_payload = filters.model_dump(exclude_none=True) if filters else None
        hits = self.index_service.search(vector=query_vector, limit=top_k, filters=filter_payload)

        return batch.provider, [
            QueryChunkResult(
                chunk_id=hit.chunk_id,
                document_id=hit.payload.get("document_id", ""),
                document_title=hit.payload.get("document_title", "Untitled Policy"),
                source_filename=hit.payload.get("source_filename", ""),
                section_path=hit.payload.get("section_path"),
                page_start=hit.payload.get("page_start", 0),
                page_end=hit.payload.get("page_end", 0),
                score=hit.score,
                text=hit.payload.get("text", ""),
                chunk_metadata=hit.payload.get("chunk_metadata", {}),
            )
            for hit in hits
        ]

