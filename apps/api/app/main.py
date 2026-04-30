import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db import SessionLocal, init_db
from app.services.hybrid_index import refresh_hybrid_index
from app.services.qdrant_index import close_qdrant_client, get_qdrant_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.prepare_runtime_directories()
    init_db()
    # Warm the process-wide Qdrant client so the embedded local store is opened
    # exactly once. Do not fail startup if Qdrant is unreachable; the per-request
    # path will surface the error.
    try:
        get_qdrant_client()
    except Exception:
        pass
    # Build the BM25 sparse index from any already-indexed chunks. Empty DB is fine.
    try:
        with SessionLocal() as db:
            refresh_hybrid_index(db)
    except Exception:
        pass
    try:
        yield
    finally:
        close_qdrant_client()


app = FastAPI(title=settings.project_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(api_router, prefix=settings.api_v1_prefix)

