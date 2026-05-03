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


class DocumentMetadataUpdate(BaseModel):
    title: str | None = None
    document_type: str | None = None
    department: str | None = None
    policy_status: str | None = None
    version_label: str | None = None
    effective_date: date | None = None
    review_date: date | None = None


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
    retrieval_mode: Literal["dense", "hybrid"] = "hybrid"
    source: Literal["manual", "suggestion"] = "manual"


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
    policy_status: str | None = None


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
    quote: str | None = None


class ConfidenceInputs(BaseModel):
    top_score: float
    score_margin: float
    unique_documents: int
    citation_count: int
    all_cited_active: bool
    evidence_bucket: Literal["high", "medium", "low"]


class EvalRunRequest(BaseModel):
    dataset: str = Field(default="medicare_starter", description="Bundled dataset name or absolute path to a JSONL file.")
    name: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    judge: bool = Field(default=True, description="Run the LLM-as-judge groundedness scorer when an OpenAI key is configured.")
    retrieval_mode: Literal["dense", "hybrid"] = "hybrid"


class EvalCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_index: int
    case_id: str
    question: str
    category: str | None
    expected_documents: list
    should_abstain: bool
    retrieved_chunk_ids: list
    retrieved_documents: list
    retrieved_scores: list
    generated_answer: str | None
    generated_citations: list
    abstained: bool | None
    confidence: str | None
    metrics: dict
    judge: dict | None
    latency_ms: int | None
    error: str | None


class EvalRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str | None
    dataset: str
    config_hash: str
    config_snapshot: dict
    status: str
    total_cases: int
    completed_cases: int
    aggregate_metrics: dict
    error: str | None
    started_at: datetime
    completed_at: datetime | None


class EvalRunDetail(EvalRunRead):
    cases: list[EvalCaseRead]


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
    confidence_inputs: ConfidenceInputs | None = None
    token_usage: dict | None = None
    suggested_questions: list[str] = Field(default_factory=list)


class QueryLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request_id: str | None
    endpoint: str
    source: str | None
    question: str
    filters: dict
    top_k: int
    retrieved_chunk_ids: list
    retrieved_documents: list
    retrieved_scores: list
    embedding_provider: str | None
    answer_model: str | None
    abstained: bool | None
    confidence: str | None
    confidence_inputs: dict | None
    citations: list
    token_usage: dict | None
    latency_ms: int | None
    status: str
    error: str | None
    created_at: datetime
