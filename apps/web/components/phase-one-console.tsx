"use client";

import { FormEvent, useState } from "react";


type UploadResult = {
  document: {
    id: string;
    title: string;
    ingestion_status: string;
    chunk_count: number;
  };
  auto_indexed: boolean;
  chunk_count: number;
  embedding_provider: string;
  embedding_dimensions: number;
};

type IndexResult = {
  chunk_count: number;
  embedding_provider: string;
  embedding_dimensions: number;
  document: {
    id: string;
    title: string;
    ingestion_status: string;
  };
};

type QueryResult = {
  question: string;
  embedding_provider: string;
  results: Array<{
    chunk_id: string;
    document_title: string;
    section_path: string | null;
    page_start: number;
    page_end: number;
    score: number;
    text: string;
  }>;
};


const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";


export function PhaseOneConsole() {
  const [file, setFile] = useState<File | null>(null);
  const [documentId, setDocumentId] = useState("");
  const [question, setQuestion] = useState("What is the urgent prior authorization escalation process?");
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [indexResult, setIndexResult] = useState<IndexResult | null>(null);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<"upload" | "index" | "query" | null>(null);

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose a PDF before uploading.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    setError(null);
    setLoading("upload");

    try {
      const response = await fetch(`${apiBaseUrl}/api/documents/upload`, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Upload failed");
      }
      setUploadResult(payload);
      setDocumentId(payload.document.id);
      setIndexResult({
        chunk_count: payload.chunk_count,
        embedding_provider: payload.embedding_provider,
        embedding_dimensions: payload.embedding_dimensions,
        document: payload.document,
      });
      setQueryResult(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Upload failed");
    } finally {
      setLoading(null);
    }
  }

  async function handleIndex() {
    if (!documentId) {
      setError("Upload a document or paste a document id first.");
      return;
    }

    setError(null);
    setLoading("index");
    try {
      const response = await fetch(`${apiBaseUrl}/api/documents/${documentId}/index`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Indexing failed");
      }
      setIndexResult(payload);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Indexing failed");
    } finally {
      setLoading(null);
    }
  }

  async function handleQuery() {
    setError(null);
    setLoading("query");
    try {
      const response = await fetch(`${apiBaseUrl}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k: 5 }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Query failed");
      }
      setQueryResult(payload);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Query failed");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
      <section className="rounded-[32px] border border-white/70 bg-paper/90 p-6 shadow-card backdrop-blur">
        <div className="mb-6 flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.26em] text-clay">Operator Console</p>
            <h2 className="font-[var(--font-display)] text-3xl font-bold text-slate">Ingest, Index, Inspect</h2>
          </div>
          <div className="rounded-full border border-slate/10 bg-sand px-4 py-2 text-sm text-slate">
            API: {apiBaseUrl}
          </div>
        </div>

        <form onSubmit={handleUpload} className="rounded-[24px] border border-slate/10 bg-white p-5">
          <label className="mb-3 block text-sm font-semibold uppercase tracking-[0.18em] text-moss">
            1. Upload PDF + Auto Index
          </label>
          <div className="flex flex-col gap-4 md:flex-row md:items-center">
            <input
              type="file"
              accept="application/pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              className="w-full rounded-2xl border border-slate/15 bg-sand px-4 py-3 text-sm text-slate"
            />
            <button
              type="submit"
              disabled={loading === "upload"}
              className="rounded-2xl bg-slate px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#101820] disabled:opacity-60"
            >
              {loading === "upload" ? "Uploading & Indexing..." : "Upload & Index"}
            </button>
          </div>
        </form>

        <div className="mt-5 rounded-[24px] border border-slate/10 bg-white p-5">
          <label className="mb-3 block text-sm font-semibold uppercase tracking-[0.18em] text-moss">
            2. Reindex Existing Document
          </label>
          <div className="flex flex-col gap-4 md:flex-row md:items-center">
            <input
              value={documentId}
              onChange={(event) => setDocumentId(event.target.value)}
              placeholder="Document id"
              className="w-full rounded-2xl border border-slate/15 bg-sand px-4 py-3 text-sm text-slate"
            />
            <button
              type="button"
              onClick={handleIndex}
              disabled={loading === "index"}
              className="rounded-2xl bg-clay px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#a45736] disabled:opacity-60"
            >
              {loading === "index" ? "Indexing..." : "Run Indexer"}
            </button>
          </div>
        </div>

        <div className="mt-5 rounded-[24px] border border-slate/10 bg-white p-5">
          <label className="mb-3 block text-sm font-semibold uppercase tracking-[0.18em] text-moss">
            3. Dense Retrieval Test
          </label>
          <div className="flex flex-col gap-4">
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              className="min-h-28 rounded-2xl border border-slate/15 bg-sand px-4 py-3 text-sm text-slate"
            />
            <button
              type="button"
              onClick={handleQuery}
              disabled={loading === "query"}
              className="w-full rounded-2xl bg-moss px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#58623f] disabled:opacity-60"
            >
              {loading === "query" ? "Querying..." : "Retrieve Top Chunks"}
            </button>
          </div>
        </div>

        {error ? (
          <div className="mt-5 rounded-2xl border border-[#d9a37f] bg-[#fff1e8] px-4 py-3 text-sm text-[#8d4d27]">
            {error}
          </div>
        ) : null}
      </section>

      <section className="space-y-5">
        <div className="rounded-[32px] border border-white/70 bg-paper/90 p-6 shadow-card backdrop-blur">
          <p className="text-sm font-medium uppercase tracking-[0.26em] text-clay">Phase 1 Status</p>
          <div className="mt-5 grid gap-4">
            <StatusRow label="Upload" value={uploadResult?.document.ingestion_status ?? "idle"} />
            <StatusRow label="Index" value={indexResult?.document.ingestion_status ?? "waiting"} />
            <StatusRow label="Embedder" value={indexResult?.embedding_provider ?? "not-run"} />
            <StatusRow label="Chunks" value={String(indexResult?.chunk_count ?? uploadResult?.document.chunk_count ?? 0)} />
          </div>
        </div>

        <div className="rounded-[32px] border border-white/70 bg-paper/90 p-6 shadow-card backdrop-blur">
          <p className="text-sm font-medium uppercase tracking-[0.26em] text-clay">Latest Retrieval</p>
          <div className="mt-4 space-y-4">
            {queryResult?.results?.length ? (
              queryResult.results.map((result) => (
                <article key={result.chunk_id} className="rounded-3xl border border-slate/10 bg-white p-4">
                  <div className="mb-3 flex items-start justify-between gap-4">
                    <div>
                      <h3 className="font-[var(--font-display)] text-lg font-semibold text-slate">
                        {result.document_title}
                      </h3>
                      <p className="text-sm text-slate/70">
                        {result.section_path ?? "General section"} | pages {result.page_start}-{result.page_end}
                      </p>
                    </div>
                    <div className="rounded-full bg-sand px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-moss">
                      {result.score.toFixed(3)}
                    </div>
                  </div>
                  <p className="line-clamp-5 text-sm leading-6 text-slate/85">{result.text}</p>
                </article>
              ))
            ) : (
              <div className="rounded-3xl border border-dashed border-slate/15 bg-white px-5 py-8 text-sm leading-6 text-slate/65">
                Upload a policy PDF and the app will index it automatically. Then run a query to inspect the top retrieved chunks.
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}


function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-2xl border border-slate/10 bg-white px-4 py-3">
      <span className="text-sm font-medium text-slate/70">{label}</span>
      <span className="rounded-full bg-sand px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-slate">
        {value}
      </span>
    </div>
  );
}
