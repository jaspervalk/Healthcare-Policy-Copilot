from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import QueryLogRead
from app.services.query_logs import get_query_log, list_query_logs


router = APIRouter()


@router.get("", response_model=list[QueryLogRead])
def list_queries(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[QueryLogRead]:
    return [QueryLogRead.model_validate(row) for row in list_query_logs(db, limit=limit, offset=offset)]


@router.get("/{log_id}", response_model=QueryLogRead)
def get_query(log_id: str, db: Session = Depends(get_db)) -> QueryLogRead:
    row = get_query_log(db, log_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query log not found")
    return QueryLogRead.model_validate(row)
