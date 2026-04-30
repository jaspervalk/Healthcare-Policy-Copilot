from __future__ import annotations

from dataclasses import dataclass

from app.schemas import AnswerCitation, QueryChunkResult


@dataclass
class CaseMetrics:
    recall_at_k: float | None
    mrr: float | None
    citation_correctness: float | None
    abstain_correct: bool | None

    def to_dict(self) -> dict:
        return {
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
            "citation_correctness": self.citation_correctness,
            "abstain_correct": self.abstain_correct,
        }


def recall_at_k_for_documents(
    retrieved_chunks: list[QueryChunkResult],
    expected_documents: list[str],
    k: int | None = None,
) -> float:
    """Document-level recall@k.

    Returns the fraction of expected_documents that appear at least once in the
    top-k retrieved chunks, by source_filename.
    """
    if not expected_documents:
        return 0.0
    chunks = retrieved_chunks if k is None else retrieved_chunks[:k]
    retrieved_filenames = {chunk.source_filename for chunk in chunks}
    found = sum(1 for doc in expected_documents if doc in retrieved_filenames)
    return found / len(expected_documents)


def mrr_for_documents(
    retrieved_chunks: list[QueryChunkResult],
    expected_documents: list[str],
) -> float:
    """Reciprocal rank of the first retrieved chunk from any expected document."""
    expected_set = set(expected_documents)
    if not expected_set:
        return 0.0
    for rank, chunk in enumerate(retrieved_chunks, start=1):
        if chunk.source_filename in expected_set:
            return 1.0 / rank
    return 0.0


def citation_correctness(
    citations: list[AnswerCitation],
    expected_documents: list[str],
) -> float:
    """Fraction of citations whose source_filename is in expected_documents."""
    if not citations:
        return 0.0
    expected_set = set(expected_documents)
    correct = sum(1 for citation in citations if citation.source_filename in expected_set)
    return correct / len(citations)


def case_metrics(
    *,
    retrieved_chunks: list[QueryChunkResult],
    citations: list[AnswerCitation],
    expected_documents: list[str],
    should_abstain: bool,
    abstained: bool,
    top_k: int,
) -> CaseMetrics:
    if should_abstain:
        # Retrieval/citation metrics are not meaningful on abstention cases:
        # the system is supposed to refuse, not retrieve evidence we trust.
        return CaseMetrics(
            recall_at_k=None,
            mrr=None,
            citation_correctness=None,
            abstain_correct=(abstained is True),
        )

    return CaseMetrics(
        recall_at_k=recall_at_k_for_documents(retrieved_chunks, expected_documents, k=top_k),
        mrr=mrr_for_documents(retrieved_chunks, expected_documents),
        citation_correctness=citation_correctness(citations, expected_documents),
        abstain_correct=(abstained is False),
    )


def aggregate_metrics(case_metric_list: list[CaseMetrics]) -> dict:
    def _mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    recalls = [m.recall_at_k for m in case_metric_list if m.recall_at_k is not None]
    mrrs = [m.mrr for m in case_metric_list if m.mrr is not None]
    citations = [m.citation_correctness for m in case_metric_list if m.citation_correctness is not None]

    abstain_results = [m.abstain_correct for m in case_metric_list if m.abstain_correct is not None]
    abstain_accuracy = (
        sum(1 for value in abstain_results if value) / len(abstain_results)
        if abstain_results
        else None
    )

    return {
        "case_count": len(case_metric_list),
        "answerable_count": len(recalls),
        "recall_at_k_mean": _mean(recalls),
        "mrr_mean": _mean(mrrs),
        "citation_correctness_mean": _mean(citations),
        "abstain_accuracy": abstain_accuracy,
    }
