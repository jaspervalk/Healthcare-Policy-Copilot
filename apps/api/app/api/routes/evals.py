from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.errors import map_exception
from app.db import get_db
from app.eval.runner import RunOptions, run_eval
from app.models import EvalRun
from app.schemas import EvalCaseRead, EvalRunDetail, EvalRunRead, EvalRunRequest


router = APIRouter()


@router.post("/run", response_model=EvalRunDetail, status_code=status.HTTP_201_CREATED)
def trigger_eval_run(request: EvalRunRequest, db: Session = Depends(get_db)) -> EvalRunDetail:
    options = RunOptions(
        dataset=request.dataset,
        name=request.name,
        top_k=request.top_k,
        judge=request.judge,
        retrieval_mode=request.retrieval_mode,
    )
    try:
        run = run_eval(db, options)
    except Exception as exc:
        raise map_exception(exc) from exc

    return _detail_payload(run)


@router.get("", response_model=list[EvalRunRead])
def list_eval_runs(db: Session = Depends(get_db)) -> list[EvalRunRead]:
    rows = db.scalars(select(EvalRun).order_by(EvalRun.started_at.desc())).all()
    return [EvalRunRead.model_validate(row) for row in rows]


@router.get("/{run_id}", response_model=EvalRunDetail)
def get_eval_run(run_id: str, db: Session = Depends(get_db)) -> EvalRunDetail:
    row = db.scalar(
        select(EvalRun).options(selectinload(EvalRun.cases)).where(EvalRun.id == run_id)
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")
    return _detail_payload(row)


def _detail_payload(run: EvalRun) -> EvalRunDetail:
    return EvalRunDetail(
        id=run.id,
        name=run.name,
        dataset=run.dataset,
        config_hash=run.config_hash,
        config_snapshot=run.config_snapshot,
        status=run.status,
        total_cases=run.total_cases,
        completed_cases=run.completed_cases,
        aggregate_metrics=run.aggregate_metrics,
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        cases=[EvalCaseRead.model_validate(case) for case in run.cases],
    )
