from fastapi import APIRouter, HTTPException, status

from app.schemas import QueryRequest, QueryResponse
from app.services.retrieval import RetrievalService


router = APIRouter()


@router.post("/query", response_model=QueryResponse)
def query_documents(request: QueryRequest) -> QueryResponse:
    try:
        retrieval_service = RetrievalService()
        provider, results = retrieval_service.search(
            question=request.question,
            top_k=request.top_k,
            filters=request.filters,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return QueryResponse(
        question=request.question,
        embedding_provider=provider,
        top_k=request.top_k,
        results=results,
    )

