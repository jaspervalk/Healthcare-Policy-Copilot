import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.query_logs as query_logs_module
from app.db import Base
from app.models import QueryLog
from app.schemas import (
    AnswerCitation,
    AnswerResponse,
    ConfidenceInputs,
    QueryChunkResult,
    QueryFilters,
    QueryResponse,
)
from app.services.query_logs import (
    get_query_log,
    list_query_logs,
    log_answer,
    log_failure,
    log_query,
)


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'qlog.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    # Redirect the query_logs module's session factory to this isolated DB.
    monkeypatch.setattr(query_logs_module, "SessionLocal", Session)
    return Session


def _chunk(chunk_id: str, source_filename: str, score: float = 0.7) -> QueryChunkResult:
    return QueryChunkResult(
        chunk_id=chunk_id,
        document_id=f"doc-{source_filename}",
        document_title=source_filename,
        source_filename=source_filename,
        section_path=None,
        page_start=1,
        page_end=1,
        score=score,
        text="...",
        chunk_metadata={},
        policy_status="active",
    )


def _citation(chunk_id: str, source_filename: str) -> AnswerCitation:
    return AnswerCitation(
        chunk_id=chunk_id,
        document_id=f"doc-{source_filename}",
        document_title=source_filename,
        source_filename=source_filename,
        section_path=None,
        page_start=1,
        page_end=1,
        score=0.7,
        quote_preview="...",
        support="supports the answer",
    )


def test_source_defaults_to_manual_when_omitted(session_factory):
    response = QueryResponse(
        question="hi", embedding_provider="local-hash", top_k=5, results=[_chunk("c1", "a.pdf")]
    )
    log_id = log_query(
        request_id=None, question="hi", filters=None, top_k=5, response=response, latency_ms=1
    )
    with session_factory() as db:
        assert get_query_log(db, log_id).source == "manual"


def test_log_answer_persists_suggestion_source(session_factory):
    response = AnswerResponse(
        question="follow up",
        answer="...",
        abstained=False,
        confidence="medium",
        confidence_reasons=[],
        answer_model="gpt-4.1-mini",
        embedding_provider="openai",
        top_k=5,
        citations=[_citation("c1", "a.pdf")],
        retrieved_chunks=[_chunk("c1", "a.pdf")],
        confidence_inputs=None,
    )
    log_id = log_answer(
        request_id=None,
        question="follow up",
        filters=None,
        top_k=5,
        response=response,
        latency_ms=10,
        source="suggestion",
    )
    with session_factory() as db:
        assert get_query_log(db, log_id).source == "suggestion"


def test_log_query_persists_retrieval_only_fields(session_factory):
    response = QueryResponse(
        question="hello",
        embedding_provider="local-hash",
        top_k=5,
        results=[_chunk("c1", "a.pdf"), _chunk("c2", "b.pdf")],
    )

    log_id = log_query(
        request_id="req-1",
        question="hello",
        filters=QueryFilters(department="utilization_management"),
        top_k=5,
        response=response,
        latency_ms=42,
    )

    assert log_id is not None

    with session_factory() as db:
        row = get_query_log(db, log_id)
        assert row is not None
        assert row.endpoint == "query"
        assert row.status == "ok"
        assert row.request_id == "req-1"
        assert row.filters == {"department": "utilization_management"}
        assert row.retrieved_chunk_ids == ["c1", "c2"]
        assert row.retrieved_documents == ["a.pdf", "b.pdf"]
        # query endpoint never carries answer-side fields
        assert row.answer_model is None
        assert row.confidence is None
        assert row.citations == []


def test_log_answer_persists_full_answer_fields(session_factory):
    response = AnswerResponse(
        question="What is X?",
        answer="X is...",
        abstained=False,
        confidence="medium",
        confidence_reasons=["evidence supports"],
        answer_model="gpt-5.4-mini",
        embedding_provider="openai",
        top_k=5,
        citations=[_citation("c1", "a.pdf")],
        retrieved_chunks=[_chunk("c1", "a.pdf"), _chunk("c2", "b.pdf")],
        confidence_inputs=ConfidenceInputs(
            top_score=0.7,
            score_margin=0.1,
            unique_documents=1,
            citation_count=1,
            all_cited_active=True,
            evidence_bucket="medium",
        ),
        token_usage={"input_tokens": 1200, "output_tokens": 80, "total_tokens": 1280},
    )

    log_id = log_answer(
        request_id="req-2",
        question="What is X?",
        filters=None,
        top_k=5,
        response=response,
        latency_ms=2345,
    )

    with session_factory() as db:
        row = get_query_log(db, log_id)
        assert row.endpoint == "answer"
        assert row.status == "ok"
        assert row.confidence == "medium"
        assert row.answer_model == "gpt-5.4-mini"
        assert row.abstained is False
        assert row.token_usage == {"input_tokens": 1200, "output_tokens": 80, "total_tokens": 1280}
        assert row.confidence_inputs["evidence_bucket"] == "medium"
        assert row.citations == [{"chunk_id": "c1", "source_filename": "a.pdf"}]


def test_log_failure_records_error_and_status(session_factory):
    log_id = log_failure(
        request_id="req-3",
        endpoint="answer",
        question="boom",
        filters=None,
        top_k=5,
        error="qdrant transport closed",
        latency_ms=12,
    )

    with session_factory() as db:
        row = get_query_log(db, log_id)
        assert row.status == "error"
        assert row.error == "qdrant transport closed"
        assert row.retrieved_chunk_ids == []


def test_list_query_logs_orders_newest_first(session_factory):
    response = QueryResponse(
        question="q1", embedding_provider="local-hash", top_k=5, results=[]
    )
    first = log_query(
        request_id=None, question="q1", filters=None, top_k=5, response=response, latency_ms=1
    )
    response2 = QueryResponse(
        question="q2", embedding_provider="local-hash", top_k=5, results=[]
    )
    second = log_query(
        request_id=None, question="q2", filters=None, top_k=5, response=response2, latency_ms=1
    )

    with session_factory() as db:
        rows = list_query_logs(db, limit=10)
        assert [row.id for row in rows[:2]] == [second, first]


def test_persist_failure_returns_none_and_does_not_raise(session_factory, monkeypatch):
    """If logging fails, the helper must swallow the error — never break the request path."""

    class _BrokenSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def add(self, _row):
            raise RuntimeError("session add failed")

        def commit(self):
            raise RuntimeError("commit failed")

        def rollback(self):
            return None

    monkeypatch.setattr(query_logs_module, "SessionLocal", lambda: _BrokenSession())

    log_id = log_failure(
        request_id=None,
        endpoint="answer",
        question="boom",
        filters=None,
        top_k=5,
        error="...",
        latency_ms=1,
    )

    assert log_id is None
