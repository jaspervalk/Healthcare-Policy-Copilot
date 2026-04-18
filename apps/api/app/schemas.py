from datetime import date, datetime
from typing import Literal

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
    auto_indexed: bool
    chunk_count: int
    embedding_provider: str
    embedding_dimensions: int


class IndexDocumentResponse(BaseModel):
    document: DocumentRead
    chunk_count: int
    embedding_provider: str
    embedding_dimensions: int


class DeleteDocumentResponse(BaseModel):
    document_id: str
    title: str
    deleted_chunk_count: int
    removed_from_index: bool
    raw_file_deleted: bool
    processed_artifact_deleted: bool


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


class AnswerRequest(QueryRequest):
    pass


class AnswerCitation(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    source_filename: str
    section_path: str | None
    page_start: int
    page_end: int
    score: float
    quote_preview: str
    support: str | None = None


class AnswerResponse(BaseModel):
    question: str
    answer: str
    abstained: bool
    confidence: Literal["high", "medium", "low"]
    confidence_reasons: list[str]
    answer_model: str
    embedding_provider: str
    top_k: int
    citations: list[AnswerCitation]
    retrieved_chunks: list[QueryChunkResult]
