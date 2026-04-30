import type {
  AnswerResult,
  DeleteResult,
  DocumentItem,
  EvalRunDetail,
  EvalRunSummary,
  QueryFilters,
  QueryLog,
  RetrievalMode,
  UploadResult,
} from "./types";


export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";


async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, init);
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail =
      (payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : null) ?? response.statusText;
    const message = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(message);
  }
  return payload as T;
}


export const api = {
  listDocuments: (): Promise<DocumentItem[]> => request("/api/documents"),

  uploadDocument: (file: File): Promise<UploadResult> => {
    const formData = new FormData();
    formData.append("file", file);
    return request("/api/documents/upload", { method: "POST", body: formData });
  },

  reindexDocument: (documentId: string): Promise<UploadResult> =>
    request(`/api/documents/${documentId}/index`, { method: "POST" }),

  patchDocument: (
    documentId: string,
    update: Partial<{
      title: string | null;
      document_type: string | null;
      department: string | null;
      policy_status: string | null;
      version_label: string | null;
      effective_date: string | null;
      review_date: string | null;
    }>,
  ): Promise<DocumentItem> =>
    request(`/api/documents/${documentId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }),

  deleteDocument: (documentId: string): Promise<DeleteResult> =>
    request(`/api/documents/${documentId}`, { method: "DELETE" }),

  answer: (params: {
    question: string;
    top_k?: number;
    filters?: QueryFilters;
    retrieval_mode?: RetrievalMode;
  }): Promise<AnswerResult> =>
    request("/api/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: params.question,
        top_k: params.top_k ?? 5,
        filters: params.filters,
        retrieval_mode: params.retrieval_mode ?? "hybrid",
      }),
    }),

  listQueries: (limit = 100): Promise<QueryLog[]> => request(`/api/queries?limit=${limit}`),

  listEvals: (): Promise<EvalRunSummary[]> => request("/api/evals"),

  getEval: (runId: string): Promise<EvalRunDetail> => request(`/api/evals/${runId}`),

  runEval: (params: {
    dataset?: string;
    name?: string;
    top_k?: number;
    judge?: boolean;
    retrieval_mode?: RetrievalMode;
  }): Promise<EvalRunDetail> =>
    request("/api/evals/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset: params.dataset ?? "medicare_starter",
        name: params.name,
        top_k: params.top_k ?? 5,
        judge: params.judge ?? true,
        retrieval_mode: params.retrieval_mode ?? "hybrid",
      }),
    }),
};
