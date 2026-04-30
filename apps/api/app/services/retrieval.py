from __future__ import annotations

from typing import Literal

from app.schemas import QueryChunkResult, QueryFilters
from app.services.embeddings import EmbeddingService
from app.services.hybrid_index import get_hybrid_index, rrf_fuse
from app.services.qdrant_index import QdrantIndexService, SearchHit


RetrievalMode = Literal["dense", "hybrid"]

# Over-fetch from each ranker before fusing so RRF has room to disagree.
_FUSION_FETCH = 30


class RetrievalService:
    def __init__(self) -> None:
        self.embedding_service = EmbeddingService()
        self.index_service = QdrantIndexService()

    def search(
        self,
        question: str,
        top_k: int,
        filters: QueryFilters | None = None,
        mode: RetrievalMode = "hybrid",
    ) -> tuple[str, list[QueryChunkResult]]:
        batch = self.embedding_service.embed_query(question)
        query_vector = batch.vectors[0]
        filter_payload = filters.model_dump(exclude_none=True) if filters else None

        if mode == "dense":
            hits = self.index_service.search(vector=query_vector, limit=top_k, filters=filter_payload)
            return batch.provider, [self._hit_to_chunk(hit) for hit in hits]

        return batch.provider, self._hybrid_search(
            question=question,
            query_vector=query_vector,
            top_k=top_k,
            filter_payload=filter_payload,
        )

    def _hybrid_search(
        self,
        *,
        question: str,
        query_vector: list[float],
        top_k: int,
        filter_payload: dict | None,
    ) -> list[QueryChunkResult]:
        hybrid_index = get_hybrid_index()

        dense_hits = self.index_service.search(
            vector=query_vector,
            limit=_FUSION_FETCH,
            filters=filter_payload,
        )
        sparse_hits = hybrid_index.search(question, limit=_FUSION_FETCH) if hybrid_index.ready else []

        # Sparse index has no metadata filter awareness yet — drop sparse-only candidates
        # that wouldn't pass the dense filter set, otherwise filtered queries become unfiltered.
        if filter_payload and sparse_hits:
            allowed_ids = {hit.chunk_id for hit in dense_hits}
            sparse_hits = [(chunk_id, score) for chunk_id, score in sparse_hits if chunk_id in allowed_ids]

        if not sparse_hits:
            # Fall back cleanly to dense-only when the sparse index has nothing to say.
            return [self._hit_to_chunk(hit) for hit in dense_hits[:top_k]]

        dense_pairs = [(hit.chunk_id, hit.score) for hit in dense_hits]
        fused = rrf_fuse(dense_pairs, sparse_hits)[:top_k]

        dense_by_id: dict[str, SearchHit] = {hit.chunk_id: hit for hit in dense_hits}

        # Resolve any sparse-only chunks via Qdrant retrieve to get full payloads.
        missing_ids = [chunk_id for chunk_id, _ in fused if chunk_id not in dense_by_id]
        if missing_ids:
            for hit in self._retrieve_payloads(missing_ids):
                dense_by_id[hit.chunk_id] = hit

        results: list[QueryChunkResult] = []
        for chunk_id, _fused_score in fused:
            hit = dense_by_id.get(chunk_id)
            if hit is None:
                continue
            results.append(self._hit_to_chunk(hit))
        return results

    def _retrieve_payloads(self, chunk_ids: list[str]) -> list[SearchHit]:
        """Fetch payloads for chunk_ids that didn't show up in the dense top-N.

        Their dense cosine score isn't returned here — we floor to 0.0 to be honest:
        sparse picked them up, dense did not within the over-fetch window.
        """
        client = self.index_service.client
        try:
            points = client.retrieve(
                collection_name=self.index_service.collection_name,
                ids=chunk_ids,
                with_payload=True,
            )
        except Exception:
            return []
        return [
            SearchHit(chunk_id=str(point.id), score=0.0, payload=point.payload or {})
            for point in points
        ]

    @staticmethod
    def _hit_to_chunk(hit: SearchHit) -> QueryChunkResult:
        return QueryChunkResult(
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
            policy_status=hit.payload.get("policy_status"),
        )
