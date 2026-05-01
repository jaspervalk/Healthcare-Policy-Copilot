"""Streaming /api/answer endpoint via Server-Sent Events.

Two-stage stream:
  1. `retrieval` — emitted once retrieval completes; payload is the retrieved chunks.
  2. `answer_delta` — zero or more events as the model emits answer-field
     characters via the streaming structured-output API.
  3. `complete` — terminal event with the full AnswerResponse.

On any failure a single terminal `error` event is emitted with the message,
and the per-request `query_logs` row is written via `log_failure(...)`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.schemas import AnswerRequest, AnswerResponse
from app.services.answer_stream import stream_compose
from app.services.answering import AnsweringService
from app.services.query_logs import log_answer, log_failure


logger = logging.getLogger(__name__)


router = APIRouter()


def _format_event(event: str, data: object) -> str:
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/answer/stream")
async def answer_stream(request: AnswerRequest, http_request: Request) -> StreamingResponse:
    request_id = getattr(http_request.state, "request_id", None)

    async def generate() -> AsyncIterator[str]:
        started = time.perf_counter()
        final_response: AnswerResponse | None = None

        try:
            service = AnsweringService()

            # Retrieval — sync; offload so we don't block the event loop.
            embedding_provider, retrieved_chunks = await asyncio.to_thread(
                service.retrieve,
                request.question,
                request.top_k,
                request.filters,
                request.retrieval_mode,
            )

            yield _format_event(
                "retrieval",
                {
                    "embedding_provider": embedding_provider,
                    "retrieval_mode": request.retrieval_mode,
                    "top_k": request.top_k,
                    "retrieved_chunks": [chunk.model_dump() for chunk in retrieved_chunks],
                },
            )

            async for event in stream_compose(
                question=request.question,
                top_k=request.top_k,
                embedding_provider=embedding_provider,
                retrieved_chunks=retrieved_chunks,
            ):
                yield _format_event(event.type, event.data)
                if event.type == "complete":
                    final_response = AnswerResponse.model_validate(event.data)
                elif event.type == "error":
                    raise RuntimeError(event.data.get("message") or "stream_compose error")

            latency_ms = int((time.perf_counter() - started) * 1000)
            if final_response is not None:
                log_answer(
                    request_id=request_id,
                    question=request.question,
                    filters=request.filters,
                    top_k=request.top_k,
                    response=final_response,
                    latency_ms=latency_ms,
                )

        except Exception as exc:  # noqa: BLE001 — terminal SSE error frame
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("Streaming answer failed: %s", exc)
            log_failure(
                request_id=request_id,
                endpoint="answer",
                question=request.question,
                filters=request.filters,
                top_k=request.top_k,
                error=str(exc),
                latency_ms=latency_ms,
            )
            yield _format_event("error", {"message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
