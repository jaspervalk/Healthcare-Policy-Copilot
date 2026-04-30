import time

from fastapi import APIRouter, Request

from app.api.errors import map_exception
from app.schemas import AnswerRequest, AnswerResponse, QueryRequest, QueryResponse
from app.services.answering import AnsweringService
from app.services.query_logs import log_answer, log_failure, log_query
from app.services.retrieval import RetrievalService


router = APIRouter()


def _request_id(http_request: Request) -> str | None:
    return getattr(http_request.state, "request_id", None)


@router.post("/query", response_model=QueryResponse)
def query_documents(request: QueryRequest, http_request: Request) -> QueryResponse:
    started = time.perf_counter()
    request_id = _request_id(http_request)
    try:
        retrieval_service = RetrievalService()
        provider, results = retrieval_service.search(
            question=request.question,
            top_k=request.top_k,
            filters=request.filters,
            mode=request.retrieval_mode,
        )
        response = QueryResponse(
            question=request.question,
            embedding_provider=provider,
            top_k=request.top_k,
            results=results,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_failure(
            request_id=request_id,
            endpoint="query",
            question=request.question,
            filters=request.filters,
            top_k=request.top_k,
            error=str(exc),
            latency_ms=latency_ms,
        )
        raise map_exception(exc) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    log_query(
        request_id=request_id,
        question=request.question,
        filters=request.filters,
        top_k=request.top_k,
        response=response,
        latency_ms=latency_ms,
    )
    return response


@router.post("/answer", response_model=AnswerResponse)
def answer_question(request: AnswerRequest, http_request: Request) -> AnswerResponse:
    started = time.perf_counter()
    request_id = _request_id(http_request)
    try:
        answer_service = AnsweringService()
        response = answer_service.answer(
            question=request.question,
            top_k=request.top_k,
            filters=request.filters,
            mode=request.retrieval_mode,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        log_failure(
            request_id=request_id,
            endpoint="answer",
            question=request.question,
            filters=request.filters,
            top_k=request.top_k,
            error=str(exc),
            latency_ms=latency_ms,
        )
        raise map_exception(exc) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    log_answer(
        request_id=request_id,
        question=request.question,
        filters=request.filters,
        top_k=request.top_k,
        response=response,
        latency_ms=latency_ms,
    )
    return response
