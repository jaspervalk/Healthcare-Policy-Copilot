from app.eval.metrics import (
    aggregate_metrics,
    case_metrics,
    citation_correctness,
    mrr_for_documents,
    recall_at_k_for_documents,
)
from app.schemas import AnswerCitation, QueryChunkResult


def _chunk(chunk_id: str, source_filename: str, score: float = 0.5) -> QueryChunkResult:
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
        score=0.5,
        quote_preview="...",
        support=None,
    )


def test_recall_at_k_hits_when_expected_doc_present():
    chunks = [_chunk("c1", "a.pdf"), _chunk("c2", "b.pdf")]

    assert recall_at_k_for_documents(chunks, ["a.pdf"], k=5) == 1.0


def test_recall_at_k_partial_when_only_some_expected_docs_match():
    chunks = [_chunk("c1", "a.pdf"), _chunk("c2", "b.pdf")]

    assert recall_at_k_for_documents(chunks, ["a.pdf", "c.pdf"], k=5) == 0.5


def test_recall_at_k_respects_k_cutoff():
    chunks = [_chunk("c1", "a.pdf"), _chunk("c2", "b.pdf")]

    assert recall_at_k_for_documents(chunks, ["b.pdf"], k=1) == 0.0


def test_mrr_returns_reciprocal_of_first_match():
    chunks = [_chunk("c1", "a.pdf"), _chunk("c2", "b.pdf"), _chunk("c3", "c.pdf")]

    assert mrr_for_documents(chunks, ["c.pdf"]) == 1 / 3


def test_mrr_zero_when_no_match():
    chunks = [_chunk("c1", "a.pdf")]

    assert mrr_for_documents(chunks, ["b.pdf"]) == 0.0


def test_citation_correctness_counts_matching_filenames():
    citations = [_citation("c1", "a.pdf"), _citation("c2", "b.pdf"), _citation("c3", "a.pdf")]

    assert citation_correctness(citations, ["a.pdf"]) == 2 / 3


def test_citation_correctness_zero_with_no_citations():
    assert citation_correctness([], ["a.pdf"]) == 0.0


def test_case_metrics_skips_retrieval_metrics_for_abstention_cases():
    metrics = case_metrics(
        retrieved_chunks=[_chunk("c1", "a.pdf")],
        citations=[_citation("c1", "a.pdf")],
        expected_documents=[],
        should_abstain=True,
        abstained=True,
        top_k=5,
    )

    assert metrics.recall_at_k is None
    assert metrics.mrr is None
    assert metrics.citation_correctness is None
    assert metrics.abstain_correct is True


def test_case_metrics_marks_abstain_wrong_when_system_answers_a_should_abstain_case():
    metrics = case_metrics(
        retrieved_chunks=[],
        citations=[],
        expected_documents=[],
        should_abstain=True,
        abstained=False,
        top_k=5,
    )

    assert metrics.abstain_correct is False


def test_aggregate_skips_none_metrics_and_computes_means():
    metrics_list = [
        case_metrics(
            retrieved_chunks=[_chunk("c1", "a.pdf")],
            citations=[_citation("c1", "a.pdf")],
            expected_documents=["a.pdf"],
            should_abstain=False,
            abstained=False,
            top_k=5,
        ),
        case_metrics(
            retrieved_chunks=[],
            citations=[],
            expected_documents=[],
            should_abstain=True,
            abstained=True,
            top_k=5,
        ),
    ]

    aggregate = aggregate_metrics(metrics_list)

    assert aggregate["case_count"] == 2
    assert aggregate["answerable_count"] == 1
    assert aggregate["recall_at_k_mean"] == 1.0
    assert aggregate["mrr_mean"] == 1.0
    assert aggregate["abstain_accuracy"] == 1.0
