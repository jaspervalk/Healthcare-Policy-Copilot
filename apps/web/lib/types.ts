export type DocumentItem = {
  id: string;
  title: string;
  source_filename: string;
  ingestion_status: string;
  document_type: string | null;
  department: string | null;
  policy_status: string | null;
  effective_date: string | null;
  review_date: string | null;
  version_label: string | null;
  page_count: number;
  parse_error: string | null;
  extracted_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  chunk_count: number;
};

export type UploadResult = {
  document: DocumentItem;
  auto_indexed: boolean;
  chunk_count: number;
  embedding_provider: string;
  embedding_dimensions: number;
};

export type DeleteResult = {
  document_id: string;
  title: string;
  deleted_chunk_count: number;
  removed_from_index: boolean;
  raw_file_deleted: boolean;
  processed_artifact_deleted: boolean;
};

export type RetrievedChunk = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  source_filename: string;
  section_path: string | null;
  page_start: number;
  page_end: number;
  score: number;
  text: string;
  chunk_metadata: Record<string, unknown>;
  policy_status: string | null;
};

export type AnswerCitation = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  source_filename: string;
  section_path: string | null;
  page_start: number;
  page_end: number;
  score: number;
  quote_preview: string;
  support: string | null;
};

export type ConfidenceInputs = {
  top_score: number;
  score_margin: number;
  unique_documents: number;
  citation_count: number;
  all_cited_active: boolean;
  evidence_bucket: "high" | "medium" | "low";
};

export type AnswerResult = {
  question: string;
  answer: string;
  abstained: boolean;
  confidence: "high" | "medium" | "low";
  confidence_reasons: string[];
  answer_model: string;
  embedding_provider: string;
  top_k: number;
  citations: AnswerCitation[];
  retrieved_chunks: RetrievedChunk[];
  confidence_inputs: ConfidenceInputs | null;
  token_usage: Record<string, number> | null;
};

export type RetrievalMode = "dense" | "hybrid";

export type QueryFilters = {
  department?: string;
  document_type?: string;
  policy_status?: string;
};

export type QueryLog = {
  id: string;
  request_id: string | null;
  endpoint: "query" | "answer";
  question: string;
  filters: Record<string, string>;
  top_k: number;
  retrieved_chunk_ids: string[];
  retrieved_documents: string[];
  retrieved_scores: number[];
  embedding_provider: string | null;
  answer_model: string | null;
  abstained: boolean | null;
  confidence: "high" | "medium" | "low" | null;
  confidence_inputs: ConfidenceInputs | null;
  citations: { chunk_id: string; source_filename: string }[];
  token_usage: Record<string, number> | null;
  latency_ms: number | null;
  status: "ok" | "error";
  error: string | null;
  created_at: string;
};

export type EvalRunSummary = {
  id: string;
  name: string | null;
  dataset: string;
  config_hash: string;
  config_snapshot: Record<string, unknown>;
  status: string;
  total_cases: number;
  completed_cases: number;
  aggregate_metrics: Record<string, number | null>;
  error: string | null;
  started_at: string;
  completed_at: string | null;
};

export type EvalCase = {
  id: string;
  case_index: number;
  case_id: string;
  question: string;
  category: string | null;
  expected_documents: string[];
  should_abstain: boolean;
  retrieved_chunk_ids: string[];
  retrieved_documents: string[];
  retrieved_scores: number[];
  generated_answer: string | null;
  generated_citations: { chunk_id: string; source_filename: string }[];
  abstained: boolean | null;
  confidence: string | null;
  metrics: Record<string, number | boolean | null>;
  judge: { verdict?: string; score?: number; reasoning?: string; model?: string } | null;
  latency_ms: number | null;
  error: string | null;
};

export type EvalRunDetail = EvalRunSummary & { cases: EvalCase[] };
