"""Tests for AnswerFieldStreamer — the JSON state machine that pulls the
top-level `answer` field's characters out of streaming structured-output deltas."""
import asyncio
import threading

import pytest

import app.services.answer_stream as answer_stream_module
from app.schemas import AnswerResponse, ConfidenceInputs
from app.services.answer_stream import AnswerFieldStreamer, stream_compose


def _feed_all(streamer: AnswerFieldStreamer, payload: str, *, chunk_size: int = 1) -> str:
    """Feed `payload` to the streamer one chunk at a time, return concatenated output."""
    out: list[str] = []
    for index in range(0, len(payload), chunk_size):
        out.append(streamer.feed(payload[index : index + chunk_size]))
    return "".join(out)


def test_extracts_answer_field_one_char_at_a_time():
    streamer = AnswerFieldStreamer()
    payload = '{"answer":"Urgent requests require review.","abstained":false,"confidence":"medium","confidence_reasons":[],"citations":[]}'

    text = _feed_all(streamer, payload, chunk_size=1)

    assert text == "Urgent requests require review."
    assert streamer.is_done


def test_extracts_answer_with_payload_split_into_arbitrary_chunks():
    streamer = AnswerFieldStreamer()
    payload = '{"answer":"Hello world","abstained":false,"confidence":"low","confidence_reasons":[],"citations":[]}'

    text = _feed_all(streamer, payload, chunk_size=7)

    assert text == "Hello world"
    assert streamer.is_done


def test_handles_escape_sequences():
    streamer = AnswerFieldStreamer()
    # Escaped newline, escaped quote, escaped backslash.
    payload = r'{"answer":"line1\nline2 with \"quote\" and \\back"}'
    # JSON in the payload is r-string so backslashes are preserved literally.

    text = _feed_all(streamer, payload, chunk_size=1)

    assert text == 'line1\nline2 with "quote" and \\back'
    assert streamer.is_done


def test_handles_unicode_escape_sequence():
    streamer = AnswerFieldStreamer()
    payload = r'{"answer":"price €10"}'  # € = €

    text = _feed_all(streamer, payload, chunk_size=1)

    assert text == "price €10"


def test_handles_unicode_split_across_chunks():
    streamer = AnswerFieldStreamer()
    # Split right in the middle of €.
    chunks = [r'{"answer":"€= \u20', "ac stops"]
    chunks[1] = chunks[1] + r'."}'

    out = ""
    for chunk in chunks:
        out += streamer.feed(chunk)

    assert out == "€= € stops."


def test_does_not_emit_after_closing_quote():
    streamer = AnswerFieldStreamer()
    payload = '{"answer":"only this","junk":"this should never leak"}'

    text = _feed_all(streamer, payload, chunk_size=1)

    assert text == "only this"


def test_handles_whitespace_around_colon_and_quote():
    streamer = AnswerFieldStreamer()
    payload = '{ "answer" : "spaced" , "abstained": false }'

    text = _feed_all(streamer, payload, chunk_size=1)

    assert text == "spaced"


def test_returns_empty_when_answer_field_absent():
    streamer = AnswerFieldStreamer()
    payload = '{"foo":"bar"}'

    text = _feed_all(streamer, payload, chunk_size=1)

    assert text == ""
    assert not streamer.is_done


def test_handles_unknown_escape_by_emitting_literal():
    streamer = AnswerFieldStreamer()
    payload = r'{"answer":"weird \x escape"}'

    text = _feed_all(streamer, payload, chunk_size=1)

    # JSON spec doesn't define \x, but we tolerate it by passing the char through.
    assert text == "weird x escape"


# ---------------------------------------------------------------------------
# N1 regression: stream_compose fallback must run sync compose off the event
# loop so concurrent streaming requests don't serialize behind one slow call.
# ---------------------------------------------------------------------------


def _stub_response(answer_text: str = "fallback answer") -> AnswerResponse:
    return AnswerResponse(
        question="q",
        answer=answer_text,
        abstained=False,
        confidence="low",
        confidence_reasons=[],
        answer_model="local-extractive",
        embedding_provider="local-hash",
        top_k=5,
        citations=[],
        retrieved_chunks=[],
        confidence_inputs=ConfidenceInputs(
            top_score=0.0,
            score_margin=0.0,
            unique_documents=0,
            citation_count=0,
            all_cited_active=False,
            evidence_bucket="low",
        ),
        token_usage=None,
    )


async def _drain(generator):
    events = []
    async for event in generator:
        events.append(event)
    return events


def test_stream_compose_empty_retrieval_runs_compose_off_event_loop(monkeypatch):
    main_thread = threading.get_ident()
    seen_threads: list[int] = []

    class _StubAnsweringService:
        def compose(self, **_kwargs):
            seen_threads.append(threading.get_ident())
            return _stub_response("empty fallback")

    monkeypatch.setattr(answer_stream_module, "AnsweringService", lambda: _StubAnsweringService())

    events = asyncio.run(
        _drain(
            stream_compose(
                question="anything",
                top_k=5,
                embedding_provider="local-hash",
                retrieved_chunks=[],
            )
        )
    )

    assert [event.type for event in events] == ["answer_delta", "complete"]
    assert seen_threads, "compose() was never called"
    assert seen_threads[0] != main_thread, "compose() ran on the event-loop thread"


def test_stream_compose_no_openai_key_runs_compose_off_event_loop(monkeypatch):
    from app.schemas import QueryChunkResult

    main_thread = threading.get_ident()
    seen_threads: list[int] = []

    class _StubAnsweringService:
        def compose(self, **_kwargs):
            seen_threads.append(threading.get_ident())
            return _stub_response("no-key fallback")

    monkeypatch.setattr(answer_stream_module, "AnsweringService", lambda: _StubAnsweringService())
    monkeypatch.setattr(answer_stream_module, "_async_client", lambda: None)

    chunks = [
        QueryChunkResult(
            chunk_id="c1",
            document_id="doc-1",
            document_title="Doc",
            source_filename="doc.pdf",
            section_path=None,
            page_start=1,
            page_end=1,
            score=0.5,
            text="evidence",
            chunk_metadata={},
            policy_status="active",
        )
    ]

    events = asyncio.run(
        _drain(
            stream_compose(
                question="anything",
                top_k=5,
                embedding_provider="local-hash",
                retrieved_chunks=chunks,
            )
        )
    )

    assert [event.type for event in events] == ["answer_delta", "complete"]
    assert seen_threads, "compose() was never called"
    assert seen_threads[0] != main_thread, "compose() ran on the event-loop thread"
