"""Token-level streaming of structured-output answers.

The OpenAI Responses API with `text_format=AnswerDraft` streams back the JSON
object character-by-character via `response.output_text.delta` events. To stream
just the user-visible answer text (and not the surrounding JSON), we run the
deltas through a small state machine that finds the top-level `"answer"` field
and emits its decoded contents.

The non-streaming JSON parse still happens at the end of the stream — we use it
to populate citations, confidence, and token usage. The streamed deltas are an
additional signal, not a replacement.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator

from app.core.config import settings
from app.schemas import AnswerCitation, AnswerResponse, QueryChunkResult
from app.services.answering import (
    AnswerDraft,
    AnsweringService,
    _extract_token_usage,
    combine_confidence,
    ensure_inline_citation_markers,
    evidence_confidence,
    sanitize_suggested_questions,
)

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None


logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    type: str
    data: dict


class AnswerFieldStreamer:
    """Pull characters from the top-level `"answer"` field of streaming JSON.

    Maintains a buffer across deltas so a key, escape, or unicode sequence
    spanning a chunk boundary is handled correctly. Once the closing quote of
    the answer value is consumed, `is_done` is True and `feed()` returns "".
    """

    _KEY_TOKEN = '"answer"'

    def __init__(self) -> None:
        self._mode: str = "search_key"
        self._key_buffer: str = ""
        self._unicode_buffer: str = ""

    @property
    def is_done(self) -> bool:
        return self._mode == "done"

    def feed(self, delta: str) -> str:
        out: list[str] = []
        for char in delta:
            if self._mode == "done":
                break
            if self._mode == "search_key":
                self._key_buffer += char
                index = self._key_buffer.find(self._KEY_TOKEN)
                if index != -1:
                    self._key_buffer = ""
                    self._mode = "after_key"
                else:
                    # Trim the buffer to avoid unbounded growth, but keep enough
                    # to match the key across a chunk boundary.
                    keep = max(0, len(self._key_buffer) - len(self._KEY_TOKEN) + 1)
                    self._key_buffer = self._key_buffer[keep:]
                continue
            if self._mode == "after_key":
                if char == ":":
                    self._mode = "before_value"
                # else: whitespace between key and colon, ignore
                continue
            if self._mode == "before_value":
                if char == '"':
                    self._mode = "in_value"
                # else: whitespace between colon and opening quote, ignore
                continue
            if self._mode == "in_value":
                if char == "\\":
                    self._mode = "escape"
                elif char == '"':
                    self._mode = "done"
                else:
                    out.append(char)
                continue
            if self._mode == "escape":
                if char == "u":
                    self._unicode_buffer = ""
                    self._mode = "unicode"
                elif char == "n":
                    out.append("\n")
                    self._mode = "in_value"
                elif char == "t":
                    out.append("\t")
                    self._mode = "in_value"
                elif char == "r":
                    out.append("\r")
                    self._mode = "in_value"
                elif char == "b":
                    out.append("\b")
                    self._mode = "in_value"
                elif char == "f":
                    out.append("\f")
                    self._mode = "in_value"
                elif char in '"\\/':
                    out.append(char)
                    self._mode = "in_value"
                else:
                    out.append(char)
                    self._mode = "in_value"
                continue
            if self._mode == "unicode":
                self._unicode_buffer += char
                if len(self._unicode_buffer) == 4:
                    try:
                        out.append(chr(int(self._unicode_buffer, 16)))
                    except ValueError:
                        pass
                    self._unicode_buffer = ""
                    self._mode = "in_value"
                continue
        return "".join(out)


def _async_client():
    if not settings.openai_api_key or AsyncOpenAI is None:
        return None
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def stream_compose(
    *,
    question: str,
    top_k: int,
    embedding_provider: str,
    retrieved_chunks: list[QueryChunkResult],
) -> AsyncIterator[StreamEvent]:
    """Yield streaming events for the compose stage.

    Sequence:
      - 0..N `answer_delta` events, each with a `{delta: str}` payload.
      - exactly 1 terminal event: `complete` (with the full AnswerResponse) or `error`.

    For the no-OpenAI fallback and the empty-retrieval abstention path we still
    yield one `answer_delta` followed by `complete`, so the frontend has a single
    rendering path.
    """
    service = AnsweringService()

    if not retrieved_chunks:
        # Sync OpenAI/embedding work — keep it off the event loop so concurrent
        # streaming requests don't serialize behind a single fallback.
        response = await asyncio.to_thread(
            service.compose,
            question=question,
            top_k=top_k,
            embedding_provider=embedding_provider,
            retrieved_chunks=[],
        )
        if response.answer:
            yield StreamEvent("answer_delta", {"delta": response.answer})
        yield StreamEvent("complete", response.model_dump())
        return

    async_client = _async_client()
    if async_client is None:
        # No real LLM available — fall back to the extractive path. Emit the
        # answer as one delta so the UI shape stays consistent.
        response = await asyncio.to_thread(
            service.compose,
            question=question,
            top_k=top_k,
            embedding_provider=embedding_provider,
            retrieved_chunks=retrieved_chunks,
        )
        if response.answer:
            yield StreamEvent("answer_delta", {"delta": response.answer})
        yield StreamEvent("complete", response.model_dump())
        return

    extractor = AnswerFieldStreamer()
    prompt = service._build_prompt(question=question, retrieved_chunks=retrieved_chunks)
    instructions = (
        "You are a healthcare policy assistant. Answer only from the supplied evidence.\n"
        "Write the answer in concise markdown — use bullet lists for multi-item answers, "
        "**bold** for important terms, short paragraphs otherwise. After every clause you "
        "draw from a chunk, write a citation marker like [1] or [1, 2]. The numbers are "
        "1-indexed positions in the citations array you return.\n"
        "For each citation, include a `quote` field with the single most relevant VERBATIM "
        "phrase copied exactly from that chunk's text — no paraphrasing, no quotation marks "
        "around it, no ellipsis. Aim for one sentence or clause, under 30 words.\n"
        "If the evidence is too thin to ground an answer, set abstained=true, return no "
        "citations, and write one short sentence saying what's missing.\n"
        "Also produce up to 3 `suggested_questions` — short, self-contained follow-up "
        "questions a healthcare admin might ask next, anchored in the same retrieved "
        "evidence. Match the language of the user's question (Dutch question → Dutch "
        "suggestions). Do not repeat the user's question."
    )

    try:
        async with async_client.responses.stream(
            model=settings.openai_answer_model,
            instructions=instructions,
            input=prompt,
            text_format=AnswerDraft,
            # See answering.py — reasoning tokens count against this budget for
            # gpt-5 family models.
            max_output_tokens=2500,
            store=False,
        ) as stream:
            async for event in stream:
                if event.type == "response.output_text.delta":
                    if extractor.is_done:
                        continue
                    chars = extractor.feed(event.delta)
                    if chars:
                        yield StreamEvent("answer_delta", {"delta": chars})
                # All other event types (created, in_progress, completed, etc.) are
                # control-plane signals; we materialize the final response below.
            final_response = await stream.get_final_response()
    except Exception as exc:
        logger.warning("Streaming compose failed, falling back to non-streaming: %s", exc)
        # Best-effort fallback: run sync compose off the event loop so a slow
        # OpenAI call doesn't block other in-flight streaming requests.
        response = await asyncio.to_thread(
            service.compose,
            question=question,
            top_k=top_k,
            embedding_provider=embedding_provider,
            retrieved_chunks=retrieved_chunks,
        )
        if response.answer:
            yield StreamEvent("answer_delta", {"delta": response.answer})
        yield StreamEvent("complete", response.model_dump())
        return

    parsed = final_response.output_parsed
    if parsed is None:
        yield StreamEvent("error", {"message": "Structured answer generation returned no parsed output."})
        return

    token_usage = _extract_token_usage(final_response)
    citations = service._citation_records(parsed.citations, retrieved_chunks)

    if parsed.abstained or not citations:
        confidence_inputs = evidence_confidence(citations=[], retrieved_chunks=retrieved_chunks)
        reasons = parsed.confidence_reasons or [
            "Model abstained or returned no citations grounded in the retrieved evidence."
        ]
        response = AnswerResponse(
            question=question,
            answer=parsed.answer.strip(),
            abstained=True,
            confidence="low",
            confidence_reasons=reasons,
            answer_model=settings.openai_answer_model,
            embedding_provider=embedding_provider,
            top_k=top_k,
            citations=[],
            retrieved_chunks=retrieved_chunks,
            confidence_inputs=confidence_inputs,
            token_usage=token_usage,
            suggested_questions=sanitize_suggested_questions(parsed.suggested_questions),
        )
    else:
        confidence_inputs = evidence_confidence(citations=citations, retrieved_chunks=retrieved_chunks)
        combined = combine_confidence(parsed.confidence, confidence_inputs.evidence_bucket)

        confidence_reasons = parsed.confidence_reasons or [
            "The answer was generated from retrieved policy evidence."
        ]
        if combined != parsed.confidence:
            confidence_reasons = [
                *confidence_reasons,
                f"Downgraded from model self-report ({parsed.confidence}) by evidence signals "
                f"(top score {confidence_inputs.top_score:.2f}, "
                f"{confidence_inputs.citation_count} citations across "
                f"{confidence_inputs.unique_documents} document"
                f"{'' if confidence_inputs.unique_documents == 1 else 's'}).",
            ]

        response = AnswerResponse(
            question=question,
            answer=ensure_inline_citation_markers(parsed.answer.strip(), len(citations)),
            abstained=False,
            confidence=combined,
            confidence_reasons=confidence_reasons,
            answer_model=settings.openai_answer_model,
            embedding_provider=embedding_provider,
            top_k=top_k,
            citations=citations,
            retrieved_chunks=retrieved_chunks,
            confidence_inputs=confidence_inputs,
            token_usage=token_usage,
            suggested_questions=sanitize_suggested_questions(parsed.suggested_questions),
        )

    yield StreamEvent("complete", response.model_dump())


# Re-export for the streaming route.
__all__ = ["AnswerFieldStreamer", "StreamEvent", "stream_compose"]
