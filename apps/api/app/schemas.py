from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    chunk_index: int
    section_path: str | None
    page_start: int
    page_end: int
    token_count: int
    text: str
    normalized_text: str
    chunk_metadata: dict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    source_filename: str
    ingestion_status: str
    document_type: str | None
    department: str | None
    policy_status: str | None
    effective_date: date | None
    review_date: date | None
    version_label: str | None
    page_count: int
    parse_error: str | None
    extracted_metadata: dict
    created_at: datetime
    updated_at: datetime
    chunk_count: int = 0


class UploadDocumentResponse(BaseModel):
    document: DocumentRead


class IndexDocumentResponse(BaseModel):
    document: DocumentRead
    chunk_count: int
    embedding_provider: str
    embedding_dimensions: int


class QueryFilters(BaseModel):
    department: str | None = None
    document_type: str | None = None
    policy_status: str | None = None


class QueryRequest(BaseModel):
    question: str = Field(min_length=3)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: QueryFilters | None = None


class QueryChunkResult(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    source_filename: str
    section_path: str | None
    page_start: int
    page_end: int
    score: float
    text: str
    chunk_metadata: dict


class QueryResponse(BaseModel):
    question: str
    embedding_provider: str
    top_k: int
    results: list[QueryChunkResult]

