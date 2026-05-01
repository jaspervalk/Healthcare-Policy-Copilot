from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), default="Untitled Policy")
    source_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(512))
    checksum: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ingestion_status: Mapped[str] = mapped_column(String(32), default="uploaded")
    document_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    policy_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    version_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="Chunk.chunk_index",
    )


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dataset: Mapped[str] = mapped_column(String(255))
    config_hash: Mapped[str] = mapped_column(String(64), index=True)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="running")
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    completed_cases: Mapped[int] = mapped_column(Integer, default=0)
    aggregate_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cases: Mapped[list["EvalCase"]] = relationship(
        "EvalCase",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="EvalCase.case_index",
    )


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True)
    case_index: Mapped[int] = mapped_column(Integer)
    case_id: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_documents: Mapped[list] = mapped_column(JSON, default=list)
    should_abstain: Mapped[bool] = mapped_column(default=False)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSON, default=list)
    retrieved_documents: Mapped[list] = mapped_column(JSON, default=list)
    retrieved_scores: Mapped[list] = mapped_column(JSON, default=list)
    generated_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_citations: Mapped[list] = mapped_column(JSON, default=list)
    abstained: Mapped[bool | None] = mapped_column(nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    judge: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[EvalRun] = relationship("EvalRun", back_populates="cases")


class QueryLog(Base):
    """One row per /api/query or /api/answer request, success or failure.

    Persists what the user asked, what we retrieved, what we returned (or why we
    failed), with enough fidelity to reconstruct the call for debugging or to
    seed an eval case.
    """

    __tablename__ = "query_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    request_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    endpoint: Mapped[str] = mapped_column(String(16), index=True)
    question: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    top_k: Mapped[int] = mapped_column(Integer)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSON, default=list)
    retrieved_documents: Mapped[list] = mapped_column(JSON, default=list)
    retrieved_scores: Mapped[list] = mapped_column(JSON, default=list)
    embedding_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    answer_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    abstained: Mapped[bool | None] = mapped_column(nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence_inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class IndexCollection(Base):
    """Stamps the active vector collection with the embedding provider/model/dim.

    Used to refuse upserts that would mix providers in a single collection. One
    row per Qdrant collection name; updated only when the collection is (re)created.
    """

    __tablename__ = "index_collections"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    dimensions: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    section_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    normalized_text: Mapped[str] = mapped_column(Text)
    chunk_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship("Document", back_populates="chunks")
