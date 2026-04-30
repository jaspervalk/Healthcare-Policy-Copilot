from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.eval.dataset import EvalCaseSpec, load_dataset
from app.eval.judge import GroundednessJudge, JudgeResult
from app.eval.metrics import CaseMetrics, aggregate_metrics, case_metrics
from app.models import EvalCase, EvalRun
from app.schemas import QueryFilters
from app.services.answering import AnsweringService
from app.services.embeddings import EmbeddingService


logger = logging.getLogger(__name__)


@dataclass
class RunOptions:
    dataset: str
    name: str | None
    top_k: int
    judge: bool
    retrieval_mode: str = "hybrid"


def _config_snapshot(options: RunOptions, dataset_path: str) -> dict:
    embedding_service = EmbeddingService()
    return {
        "dataset": dataset_path,
        "top_k": options.top_k,
        "judge_enabled": options.judge,
        "retrieval_mode": options.retrieval_mode,
        "embedding": {
            "provider": embedding_service.configured_provider,
            "model": embedding_service.configured_model,
            "dimensions": settings.openai_embedding_dimensions
            if embedding_service.client is not None
            else settings.local_embedding_dimensions,
        },
        "answer_model": settings.openai_answer_model if embedding_service.client is not None else "local-extractive",
    }


def _config_hash(snapshot: dict) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def run_eval(db: Session, options: RunOptions) -> EvalRun:
    dataset_path, specs = load_dataset(options.dataset)
    snapshot = _config_snapshot(options, str(dataset_path))
    config_hash = _config_hash(snapshot)

    run = EvalRun(
        name=options.name,
        dataset=str(dataset_path),
        config_hash=config_hash,
        config_snapshot=snapshot,
        status="running",
        total_cases=len(specs),
        completed_cases=0,
        aggregate_metrics={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    answering_service = AnsweringService()
    judge = GroundednessJudge() if options.judge else None

    case_metric_list: list[CaseMetrics] = []
    judge_scores: list[int] = []

    try:
        for index, spec in enumerate(specs):
            case_metrics_obj, judge_result = _run_one(
                spec=spec,
                top_k=options.top_k,
                answering_service=answering_service,
                judge=judge,
                retrieval_mode=options.retrieval_mode,
            )

            metrics_dict = case_metrics_obj.metrics.to_dict()
            if judge_result is not None and judge_result.score is not None:
                judge_scores.append(judge_result.score)
            row = EvalCase(
                run_id=run.id,
                case_index=index,
                case_id=spec.case_id,
                question=spec.question,
                category=spec.category,
                expected_documents=spec.expected_documents,
                should_abstain=spec.should_abstain,
                retrieved_chunk_ids=case_metrics_obj.retrieved_chunk_ids,
                retrieved_documents=case_metrics_obj.retrieved_documents,
                retrieved_scores=case_metrics_obj.retrieved_scores,
                generated_answer=case_metrics_obj.generated_answer,
                generated_citations=case_metrics_obj.generated_citations,
                abstained=case_metrics_obj.abstained,
                confidence=case_metrics_obj.confidence,
                metrics=metrics_dict,
                judge=judge_result.to_dict() if judge_result is not None else None,
                latency_ms=case_metrics_obj.latency_ms,
                error=case_metrics_obj.error,
            )
            db.add(row)
            run.completed_cases = index + 1
            db.commit()

            case_metric_list.append(case_metrics_obj.metrics)

        aggregate = aggregate_metrics(case_metric_list)
        if judge_scores:
            aggregate["judge_score_mean"] = sum(judge_scores) / len(judge_scores)
            aggregate["judge_score_count"] = len(judge_scores)

        run.aggregate_metrics = aggregate
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.completed_at = datetime.utcnow()
        db.commit()
        raise

    return run


@dataclass
class _CaseOutcome:
    metrics: CaseMetrics
    retrieved_chunk_ids: list[str]
    retrieved_documents: list[str]
    retrieved_scores: list[float]
    generated_answer: str | None
    generated_citations: list[dict]
    abstained: bool | None
    confidence: str | None
    latency_ms: int | None
    error: str | None


def _run_one(
    *,
    spec: EvalCaseSpec,
    top_k: int,
    answering_service: AnsweringService,
    judge: GroundednessJudge | None,
    retrieval_mode: str = "hybrid",
) -> tuple[_CaseOutcome, JudgeResult | None]:
    started = time.perf_counter()
    try:
        response = answering_service.answer(
            question=spec.question,
            top_k=top_k,
            filters=QueryFilters(),
            mode=retrieval_mode,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.warning("Eval case %s failed: %s", spec.case_id, exc)
        return (
            _CaseOutcome(
                metrics=CaseMetrics(
                    recall_at_k=None,
                    mrr=None,
                    citation_correctness=None,
                    abstain_correct=None,
                ),
                retrieved_chunk_ids=[],
                retrieved_documents=[],
                retrieved_scores=[],
                generated_answer=None,
                generated_citations=[],
                abstained=None,
                confidence=None,
                latency_ms=latency_ms,
                error=str(exc),
            ),
            None,
        )

    latency_ms = int((time.perf_counter() - started) * 1000)

    metrics = case_metrics(
        retrieved_chunks=response.retrieved_chunks,
        citations=response.citations,
        expected_documents=spec.expected_documents,
        should_abstain=spec.should_abstain,
        abstained=response.abstained,
        top_k=top_k,
    )

    judge_result: JudgeResult | None = None
    if judge is not None and not spec.should_abstain and not response.abstained:
        judge_result = judge.score(
            question=spec.question,
            answer=response.answer,
            retrieved_chunks=response.retrieved_chunks,
        )

    return (
        _CaseOutcome(
            metrics=metrics,
            retrieved_chunk_ids=[chunk.chunk_id for chunk in response.retrieved_chunks],
            retrieved_documents=[chunk.source_filename for chunk in response.retrieved_chunks],
            retrieved_scores=[chunk.score for chunk in response.retrieved_chunks],
            generated_answer=response.answer,
            generated_citations=[citation.model_dump() for citation in response.citations],
            abstained=response.abstained,
            confidence=response.confidence,
            latency_ms=latency_ms,
            error=None,
        ),
        judge_result,
    )
