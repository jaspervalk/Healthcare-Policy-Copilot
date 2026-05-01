from fastapi import APIRouter

from app.api.routes import documents, evals, health, queries, query, stream


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(query.router, tags=["query"])
api_router.include_router(stream.router, tags=["query"])
api_router.include_router(queries.router, prefix="/queries", tags=["queries"])
api_router.include_router(evals.router, prefix="/evals", tags=["evals"])

