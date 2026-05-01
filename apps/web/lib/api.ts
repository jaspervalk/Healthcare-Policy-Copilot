import type {
  AnswerResult,
  DeleteResult,
  DocumentItem,
  EvalRunDetail,
  EvalRunSummary,
  QueryFilters,
  QueryLog,
  RetrievalMode,
  RetrievedChunk,
  UploadResult,
} from "./types";


export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";


export type StreamHandlers = {
  onRetrieval: (payload: {
    embedding_provider: string;
    retrieval_mode: RetrievalMode;
    top_k: number;
    retrieved_chunks: RetrievedChunk[];
  }) => void;
  onAnswerDelta: (delta: string) => void;
  onComplete: (response: AnswerResult) => void;
  onError: (message: string) => void;
};


/**
 * Open an SSE stream against /api/answer/stream and dispatch events to handlers.
 * Returns an `abort()` function the caller can use to cancel the request.
 */
async function streamAnswer(
  params: {
    question: string;
    top_k?: number;
    filters?: QueryFilters;
    retrieval_mode?: RetrievalMode;
  },
  handlers: StreamHandlers,
): Promise<void> {
  const controller = new AbortController();
  let cancelled = false;

  const cleanup = () => {
    cancelled = true;
    controller.abort();
  };

  try {
    const response = await fetch(`${apiBaseUrl}/api/answer/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        question: params.question,
        top_k: params.top_k ?? 5,
        filters: params.filters,
        retrieval_mode: params.retrieval_mode ?? "hybrid",
      }),
      signal: controller.signal,
    });

    if (!response.ok || !response.body) {
      const text = await response.text().catch(() => "");
      handlers.onError(text || `HTTP ${response.status}`);
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (!cancelled) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let separatorIndex = buffer.indexOf("\n\n");
      while (separatorIndex !== -1) {
        const rawEvent = buffer.slice(0, separatorIndex);
        buffer = buffer.slice(separatorIndex + 2);

        const event = parseSseEvent(rawEvent);
        if (event) {
          dispatch(event, handlers);
        }
        separatorIndex = buffer.indexOf("\n\n");
      }
    }
  } catch (error) {
    if (!controller.signal.aborted) {
      handlers.onError(error instanceof Error ? error.message : "Stream failed");
    }
  } finally {
    cleanup();
  }
}


function parseSseEvent(raw: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}


function dispatch(event: { event: string; data: unknown }, handlers: StreamHandlers) {
  if (event.event === "retrieval") {
    handlers.onRetrieval(event.data as Parameters<StreamHandlers["onRetrieval"]>[0]);
  } else if (event.event === "answer_delta") {
    const data = event.data as { delta?: string };
    if (typeof data?.delta === "string") {
      handlers.onAnswerDelta(data.delta);
    }
  } else if (event.event === "complete") {
    handlers.onComplete(event.data as AnswerResult);
  } else if (event.event === "error") {
    const data = event.data as { message?: string };
    handlers.onError(data?.message ?? "Stream error");
  }
}


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

  streamAnswer: streamAnswer,

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
