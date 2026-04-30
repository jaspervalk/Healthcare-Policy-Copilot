from __future__ import annotations

import logging
from typing import Any

from app.db import SessionLocal
from app.models import QueryLog
from app.schemas import AnswerResponse, QueryFilters, QueryResponse


logger = logging.getLogger(__name__)


def _filters_dict(filters: QueryFilters | None) -> dict:
    return filters.model_dump(exclude_none=True) if filters else {}


def _safe_persist(row: QueryLog) -> str | None:
    """Persist on a fresh session so logging cannot poison the request transaction."""
    try:
        with SessionLocal() as session:
            session.add(row)
            session.commit()
            return row.id
    except Exception:
        logger.exception("query log persist failed")
        return None


def log_query(
    *,
    request_id: str | None,
    question: str,
    filters: QueryFilters | None,
    top_k: int,
    response: QueryResponse,
    latency_ms: int,
) -> str | None:
    row = QueryLog(
        request_id=request_id,
        endpoint="query",
        question=question,
        filters=_filters_dict(filters),
        top_k=top_k,
        retrieved_chunk_ids=[chunk.chunk_id for chunk in response.results],
        retrieved_documents=[chunk.source_filename for chunk in response.results],
        retrieved_scores=[chunk.score for chunk in response.results],
        embedding_provider=response.embedding_provider,
        answer_model=None,
        abstained=None,
        confidence=None,
        confidence_inputs=None,
        citations=[],
        token_usage=None,
        latency_ms=latency_ms,
        status="ok",
        error=None,
    )
    return _safe_persist(row)


def log_answer(
    *,
    request_id: str | None,
    question: str,
    filters: QueryFilters | None,
    top_k: int,
    response: AnswerResponse,
    latency_ms: int,
) -> str | None:
    row = QueryLog(
        request_id=request_id,
        endpoint="answer",
        question=question,
        filters=_filters_dict(filters),
        top_k=top_k,
        retrieved_chunk_ids=[chunk.chunk_id for chunk in response.retrieved_chunks],
        retrieved_documents=[chunk.source_filename for chunk in response.retrieved_chunks],
        retrieved_scores=[chunk.score for chunk in response.retrieved_chunks],
        embedding_provider=response.embedding_provider,
        answer_model=response.answer_model,
        abstained=response.abstained,
        confidence=response.confidence,
        confidence_inputs=response.confidence_inputs.model_dump() if response.confidence_inputs else None,
        citations=[
            {"chunk_id": citation.chunk_id, "source_filename": citation.source_filename}
            for citation in response.citations
        ],
        token_usage=response.token_usage,
        latency_ms=latency_ms,
        status="ok",
        error=None,
    )
    return _safe_persist(row)


def log_failure(
    *,
    request_id: str | None,
    endpoint: str,
    question: str,
    filters: QueryFilters | None,
    top_k: int,
    error: str,
    latency_ms: int,
) -> str | None:
    row = QueryLog(
        request_id=request_id,
        endpoint=endpoint,
        question=question,
        filters=_filters_dict(filters),
        top_k=top_k,
        retrieved_chunk_ids=[],
        retrieved_documents=[],
        retrieved_scores=[],
        embedding_provider=None,
        answer_model=None,
        abstained=None,
        confidence=None,
        confidence_inputs=None,
        citations=[],
        token_usage=None,
        latency_ms=latency_ms,
        status="error",
        error=error,
    )
    return _safe_persist(row)


def list_query_logs(db: Any, *, limit: int = 100, offset: int = 0) -> list[QueryLog]:
    from sqlalchemy import select

    stmt = (
        select(QueryLog)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


def get_query_log(db: Any, log_id: str) -> QueryLog | None:
    from sqlalchemy import select

    return db.scalar(select(QueryLog).where(QueryLog.id == log_id))
