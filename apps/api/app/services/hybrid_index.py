"""In-memory BM25 sparse index over indexed chunks.

Rebuilt from SQL on startup and after every ingest/reindex/delete. Kept
intentionally simple — for portfolio scale (tens of docs, hundreds of chunks)
this fits comfortably in memory and rebuilds in milliseconds.
"""
from __future__ import annotations

import logging
import re
import threading

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document


logger = logging.getLogger(__name__)


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "of", "in", "on", "for", "to", "from", "with", "by", "as", "at",
        "and", "or", "but", "if", "this", "that", "these", "those",
        "it", "its", "into", "than", "then", "there", "their", "they",
        "such", "may", "shall", "must", "can",
    }
)


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS]


class HybridIndex:
    """BM25 over chunk normalized_text, keyed by chunk_id."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._chunk_ids: list[str] = []
        self._bm25: BM25Okapi | None = None
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    @property
    def ready(self) -> bool:
        return self._bm25 is not None

    def rebuild_from_sql(self, db: Session) -> int:
        """Rebuild over chunks from documents whose ingestion_status is 'indexed'."""
        stmt = (
            select(Chunk)
            .join(Document, Chunk.document_id == Document.id)
            .where(Document.ingestion_status == "indexed")
        )
        chunks = list(db.scalars(stmt))

        with self._lock:
            if not chunks:
                self._chunk_ids = []
                self._bm25 = None
                self._size = 0
                return 0

            tokenized: list[list[str]] = []
            ids: list[str] = []
            for chunk in chunks:
                tokens = tokenize(chunk.normalized_text)
                if not tokens:
                    continue
                tokenized.append(tokens)
                ids.append(chunk.id)

            if not tokenized:
                self._chunk_ids = []
                self._bm25 = None
                self._size = 0
                return 0

            self._chunk_ids = ids
            self._bm25 = BM25Okapi(tokenized)
            self._size = len(ids)
        return self._size

    def search(self, query: str, limit: int) -> list[tuple[str, float]]:
        with self._lock:
            if self._bm25 is None or not self._chunk_ids:
                return []
            tokens = tokenize(query)
            if not tokens:
                return []
            scores = self._bm25.get_scores(tokens)
            ranked = sorted(
                zip(self._chunk_ids, scores, strict=True),
                key=lambda item: item[1],
                reverse=True,
            )
        # BM25Okapi can produce zero or negative IDFs in tiny corpora where most terms
        # appear in most documents; ranking still holds, so don't cut on absolute score.
        return [(chunk_id, float(score)) for chunk_id, score in ranked[:limit]]


_index: HybridIndex | None = None
_index_lock = threading.Lock()


def get_hybrid_index() -> HybridIndex:
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                _index = HybridIndex()
    return _index


def refresh_hybrid_index(db: Session) -> int:
    try:
        return get_hybrid_index().rebuild_from_sql(db)
    except Exception:
        logger.exception("Hybrid index refresh failed; sparse retrieval will be unavailable.")
        return 0


def reset_hybrid_index() -> None:
    """Test helper — drop the singleton so monkeypatched globals don't leak across tests."""
    global _index
    with _index_lock:
        _index = None


def rrf_fuse(
    dense: list[tuple[str, float]],
    sparse: list[tuple[str, float]],
    *,
    k: int = 60,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion.

    Each ranker contributes 1 / (k + rank). Inputs must be pre-sorted descending
    by their native score; only the rank position is used.
    """
    fused: dict[str, float] = {}
    for rank, (chunk_id, _) in enumerate(dense, start=1):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k + rank)
    for rank, (chunk_id, _) in enumerate(sparse, start=1):
        fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda item: item[1], reverse=True)
