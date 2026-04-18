from app.schemas import QueryChunkResult
from app.services.answering import AnsweringService


def test_fallback_answer_uses_top_chunk_and_citations():
    service = AnsweringService()
    retrieved_chunks = [
        QueryChunkResult(
            chunk_id="chunk-1",
            document_id="doc-1",
            document_title="Prior Authorization Policy",
            source_filename="prior-auth.pdf",
            section_path="1. Urgent Requests",
            page_start=2,
            page_end=3,
            score=0.88,
            text="Urgent requests require medical director review within four hours.",
            chunk_metadata={},
        )
    ]

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
