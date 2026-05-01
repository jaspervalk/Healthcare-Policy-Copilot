import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.eval.runner import RunOptions, run_eval
from app.schemas import AnswerResponse, ConfidenceInputs, QueryChunkResult, QueryFilters


def _setup_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'eval.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _chunk(source_filename: str, chunk_id: str = "c1") -> QueryChunkResult:
    return QueryChunkResult(
        chunk_id=chunk_id,
        document_id=f"doc-{source_filename}",
        document_title=source_filename,
        source_filename=source_filename,
        section_path=None,
        page_start=1,
        page_end=1,
        score=0.7,
        text="evidence text",
        chunk_metadata={},
        policy_status="active",
    )


class _StubAnsweringService:
    """Returns scripted AnswerResponses based on the question text."""

    def __init__(self, scripted: dict[str, AnswerResponse]) -> None:
        self.scripted = scripted

    def answer(
        self,
        *,
        question: str,
        top_k: int,
        filters: QueryFilters | None = None,
        mode: str = "hybrid",
    ) -> AnswerResponse:
        return self.scripted[question]


@pytest.fixture
def dataset_file(tmp_path, monkeypatch):
    """Stage a JSONL dataset under a sandboxed DATASETS_DIR.

    The dataset resolver (R4 hardening) rejects absolute paths and `..`
    segments, so tests must reach the file via a bundled-style name.
    Monkeypatching DATASETS_DIR lets us keep test fixtures isolated.
    """
    path = tmp_path / "mini.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"id": "q1", "question": "What is in chapter 1?", "category": "direct_lookup", "expected_documents": ["bp102c01.pdf"], "should_abstain": false}',
                '{"id": "q2", "question": "Out of scope question?", "category": "abstention", "expected_documents": [], "should_abstain": true}',
            ]
        ),
        encoding="utf-8",
    )
    import app.eval.dataset as dataset_module

    monkeypatch.setattr(dataset_module, "DATASETS_DIR", tmp_path)
    return "mini"


def test_run_eval_persists_run_with_aggregate_metrics(dataset_file, tmp_path, monkeypatch):
    SessionLocal = _setup_db(tmp_path)

    scripted = {
        "What is in chapter 1?": AnswerResponse(
            question="What is in chapter 1?",
            answer="Inpatient hospital coverage requires...",
            abstained=False,
            confidence="medium",
            confidence_reasons=[],
            answer_model="stub",
            embedding_provider="local-hash",
            top_k=5,
            citations=[],
            retrieved_chunks=[_chunk("bp102c01.pdf")],
            confidence_inputs=ConfidenceInputs(
                top_score=0.7,
                score_margin=0.2,
                unique_documents=1,
                citation_count=0,
                all_cited_active=False,
                evidence_bucket="medium",
            ),
        ),
        "Out of scope question?": AnswerResponse(
            question="Out of scope question?",
            answer="No supporting evidence.",
            abstained=True,
            confidence="low",
            confidence_reasons=["nothing relevant"],
            answer_model="stub",
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
        ),
    }

    monkeypatch.setattr(
        "app.eval.runner.AnsweringService",
        lambda: _StubAnsweringService(scripted),
    )

    # Skip the LLM judge regardless of any ambient OPENAI_API_KEY.
    options = RunOptions(dataset=dataset_file, name="test", top_k=5, judge=False)

    with SessionLocal() as db:
        run = run_eval(db, options)

    assert run.status == "completed"
    assert run.total_cases == 2
    assert run.completed_cases == 2
    assert run.aggregate_metrics["case_count"] == 2
    assert run.aggregate_metrics["answerable_count"] == 1
    assert run.aggregate_metrics["recall_at_k_mean"] == 1.0
    assert run.aggregate_metrics["abstain_accuracy"] == 1.0

    with SessionLocal() as db:
        from app.models import EvalCase, EvalRun
        from sqlalchemy import select

        cases = list(
            db.scalars(
                select(EvalCase).where(EvalCase.run_id == run.id).order_by(EvalCase.case_index)
            )
        )
        assert [c.case_id for c in cases] == ["q1", "q2"]
        assert cases[0].metrics["recall_at_k"] == 1.0
        assert cases[0].abstained is False
        assert cases[1].abstained is True
        assert cases[1].metrics["abstain_correct"] is True

        # Same config -> same hash on a re-run
        run_again = run_eval(db, options)
        assert run_again.config_hash == run.config_hash
