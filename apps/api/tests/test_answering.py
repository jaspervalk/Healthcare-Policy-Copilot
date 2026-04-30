from app.schemas import AnswerCitation, QueryChunkResult
from app.services.answering import (
    AnswerDraft,
    AnsweringService,
    combine_confidence,
    evidence_confidence,
)


def _chunk(
    *,
    chunk_id: str,
    document_id: str = "doc-1",
    score: float = 0.5,
    policy_status: str | None = "active",
) -> QueryChunkResult:
    return QueryChunkResult(
        chunk_id=chunk_id,
        document_id=document_id,
        document_title="Prior Authorization Policy",
        source_filename="prior-auth.pdf",
        section_path="1. Urgent Requests",
        page_start=2,
        page_end=3,
        score=score,
        text="Urgent requests require medical director review within four hours.",
        chunk_metadata={},
        policy_status=policy_status,
    )


def _citation(chunk_id: str, document_id: str = "doc-1") -> AnswerCitation:
    return AnswerCitation(
        chunk_id=chunk_id,
        document_id=document_id,
        document_title="Prior Authorization Policy",
        source_filename="prior-auth.pdf",
        section_path="1. Urgent Requests",
        page_start=2,
        page_end=3,
        score=0.6,
        quote_preview="Urgent requests require medical director review.",
        support=None,
    )


class _FakeResponse:
    def __init__(self, draft: AnswerDraft) -> None:
        self.output_parsed = draft


class _FakeResponses:
    def __init__(self, draft: AnswerDraft) -> None:
        self._draft = draft

    def parse(self, **_kwargs) -> _FakeResponse:
        return _FakeResponse(self._draft)


class _FakeOpenAIClient:
    def __init__(self, draft: AnswerDraft) -> None:
        self.responses = _FakeResponses(draft)


def test_fallback_answer_uses_top_chunk_and_citations():
    service = AnsweringService()
    retrieved_chunks = [_chunk(chunk_id="chunk-1", score=0.88)]

    response = service._fallback_answer(
        question="What happens to urgent requests?",
        top_k=5,
        embedding_provider="local-hash",
        retrieved_chunks=retrieved_chunks,
    )

    assert response.answer_model == "local-extractive"
    assert response.abstained is False
    assert response.citations[0].chunk_id == "chunk-1"
    assert "Urgent requests require medical director review" in response.answer
    assert response.confidence_inputs is not None
    assert response.confidence_inputs.citation_count == 1


def test_evidence_confidence_is_low_with_no_citations():
    chunks = [_chunk(chunk_id="c1", score=0.9)]

    inputs = evidence_confidence(citations=[], retrieved_chunks=chunks)

    assert inputs.evidence_bucket == "low"
    assert inputs.citation_count == 0
    assert inputs.unique_documents == 0
    assert inputs.all_cited_active is False


def test_evidence_confidence_is_medium_with_one_citation_at_ok_score():
    chunks = [_chunk(chunk_id="c1", score=0.4)]

    inputs = evidence_confidence(citations=[_citation("c1")], retrieved_chunks=chunks)

    assert inputs.evidence_bucket == "medium"
    assert inputs.citation_count == 1
    assert inputs.unique_documents == 1


def test_evidence_confidence_high_needs_two_citations_strong_score_and_active():
    chunks = [
        _chunk(chunk_id="c1", score=0.7),
        _chunk(chunk_id="c2", document_id="doc-2", score=0.6),
    ]
    citations = [_citation("c1"), _citation("c2", document_id="doc-2")]

    inputs = evidence_confidence(citations=citations, retrieved_chunks=chunks)

    assert inputs.evidence_bucket == "high"
    assert inputs.unique_documents == 2
    assert inputs.all_cited_active is True


def test_evidence_confidence_drops_to_medium_if_a_cited_chunk_is_retired():
    chunks = [
        _chunk(chunk_id="c1", score=0.7),
        _chunk(chunk_id="c2", document_id="doc-2", score=0.6, policy_status="retired"),
    ]
    citations = [_citation("c1"), _citation("c2", document_id="doc-2")]

    inputs = evidence_confidence(citations=citations, retrieved_chunks=chunks)

    assert inputs.all_cited_active is False
    assert inputs.evidence_bucket == "medium"


def test_evidence_confidence_drops_to_low_when_top_score_is_weak():
    chunks = [_chunk(chunk_id="c1", score=0.2)]

    inputs = evidence_confidence(citations=[_citation("c1")], retrieved_chunks=chunks)

    assert inputs.evidence_bucket == "low"


def test_combine_confidence_takes_the_minimum():
    assert combine_confidence("high", "low") == "low"
    assert combine_confidence("medium", "high") == "medium"
    assert combine_confidence("high", "high") == "high"
    assert combine_confidence("low", "medium") == "low"


def test_answer_returns_no_citations_and_low_confidence_when_model_cites_nothing(monkeypatch):
    service = AnsweringService()
    chunks = [_chunk(chunk_id="c1", score=0.7), _chunk(chunk_id="c2", score=0.6)]
    monkeypatch.setattr(
        service.retrieval_service,
        "search",
        lambda question, top_k, filters, mode="hybrid": ("local-hash", chunks),
    )
    service.client = _FakeOpenAIClient(
        AnswerDraft(
            answer="Plausible-sounding text without grounded citations.",
            abstained=False,
            confidence="high",
            confidence_reasons=["model claims it knows"],
            citations=[],
        )
    )

    response = service.answer(question="What is the escalation path?", top_k=5)

    assert response.citations == []
    assert response.confidence == "low"
    assert response.abstained is True
    assert response.confidence_inputs is not None
    assert response.confidence_inputs.citation_count == 0


def test_answer_downgrades_high_model_confidence_when_evidence_is_weak(monkeypatch):
    service = AnsweringService()
    chunks = [_chunk(chunk_id="c1", score=0.2)]
    monkeypatch.setattr(
        service.retrieval_service,
        "search",
        lambda question, top_k, filters, mode="hybrid": ("local-hash", chunks),
    )

    from app.services.answering import AnswerCitationDraft

    service.client = _FakeOpenAIClient(
        AnswerDraft(
            answer="Grounded answer text.",
            abstained=False,
            confidence="high",
            confidence_reasons=[],
            citations=[AnswerCitationDraft(chunk_id="c1", support="supports the answer")],
        )
    )

    response = service.answer(question="Anything?", top_k=5)

    assert response.confidence == "low"
    assert len(response.citations) == 1
    assert response.confidence_inputs.evidence_bucket == "low"
    assert any("Downgraded" in reason for reason in response.confidence_reasons)


def test_answer_keeps_model_confidence_when_evidence_supports_it(monkeypatch):
    service = AnsweringService()
    chunks = [
        _chunk(chunk_id="c1", score=0.7),
        _chunk(chunk_id="c2", document_id="doc-2", score=0.6),
    ]
    monkeypatch.setattr(
        service.retrieval_service,
        "search",
        lambda question, top_k, filters, mode="hybrid": ("local-hash", chunks),
    )

    from app.services.answering import AnswerCitationDraft

    service.client = _FakeOpenAIClient(
        AnswerDraft(
            answer="Grounded answer text.",
            abstained=False,
            confidence="medium",
            confidence_reasons=[],
            citations=[
                AnswerCitationDraft(chunk_id="c1", support="supports A"),
                AnswerCitationDraft(chunk_id="c2", support="supports B"),
            ],
        )
    )

    response = service.answer(question="Anything?", top_k=5)

    # Evidence bucket would be "high" but the model self-reported "medium" — combined = medium.
    assert response.confidence == "medium"
    assert len(response.citations) == 2
    assert response.confidence_inputs.evidence_bucket == "high"


def test_answer_respects_model_abstention_even_with_citations(monkeypatch):
    service = AnsweringService()
    chunks = [_chunk(chunk_id="c1", score=0.7)]
    monkeypatch.setattr(
        service.retrieval_service,
        "search",
        lambda question, top_k, filters, mode="hybrid": ("local-hash", chunks),
    )

    from app.services.answering import AnswerCitationDraft

    service.client = _FakeOpenAIClient(
        AnswerDraft(
            answer="The evidence does not directly answer this question.",
            abstained=True,
            confidence="medium",
            confidence_reasons=["weak evidence"],
            citations=[AnswerCitationDraft(chunk_id="c1", support="tangentially related")],
        )
    )

    response = service.answer(question="Anything?", top_k=5)

    assert response.abstained is True
    assert response.citations == []
    assert response.confidence == "low"
