"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Banner } from "@/components/ui/banner";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import type { QueryLog } from "@/lib/types";


export function QueriesFeed() {
  const [logs, setLogs] = useState<QueryLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "answer" | "query" | "error">("all");

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      setLogs(await api.listQueries(200));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load queries.");
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    if (filter === "all") return logs;
    if (filter === "error") return logs.filter((log) => log.status === "error");
    return logs.filter((log) => log.endpoint === filter);
  }, [logs, filter]);

  const selected = useMemo(() => logs.find((log) => log.id === selectedId) ?? null, [logs, selectedId]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ink-900">Queries</h1>
          <p className="mt-1 text-sm text-ink-500">
            {logs.length} request{logs.length === 1 ? "" : "s"} logged. Newest first.
          </p>
        </div>
        <FilterBar value={filter} onChange={setFilter} />
      </header>

      {error ? <Banner tone="danger" className="mb-3">{error}</Banner> : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="overflow-hidden rounded-lg border border-ink-100 bg-white">
          {loading && logs.length === 0 ? (
            <div className="space-y-2 p-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={index} className="h-12 animate-pulse rounded-md bg-ink-50" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="px-4 py-12">
              <EmptyState title="No queries match" description="Adjust the filter, or run an answer to populate the feed." />
            </div>
          ) : (
            <ol className="divide-y divide-ink-100">
              {filtered.map((log) => (
                <li key={log.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedId(log.id)}
                    className={`flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition ${
                      selectedId === log.id ? "bg-ink-50" : "hover:bg-ink-50/60"
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-ink-900">{log.question}</p>
                      <p className="mt-0.5 text-xs text-ink-500">
                        {formatDate(log.created_at)} · {log.endpoint} · {log.latency_ms ?? "?"} ms
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Badge tone={log.status === "ok" ? "success" : "danger"}>{log.status}</Badge>
                      {log.confidence ? (
                        <Badge tone={confidenceTone(log.confidence)}>{log.confidence}</Badge>
                      ) : null}
                    </div>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>

        <QueryDetail log={selected} />
      </div>
    </div>
  );
}


function FilterBar({
  value,
  onChange,
}: {
  value: "all" | "answer" | "query" | "error";
  onChange: (value: "all" | "answer" | "query" | "error") => void;
}) {
  const options: { key: "all" | "answer" | "query" | "error"; label: string }[] = [
    { key: "all", label: "All" },
    { key: "answer", label: "Answer" },
    { key: "query", label: "Query" },
    { key: "error", label: "Errors" },
  ];
  return (
    <div className="inline-flex rounded-md border border-ink-200 p-0.5">
      {options.map((option) => (
        <button
          key={option.key}
          type="button"
          onClick={() => onChange(option.key)}
          aria-pressed={value === option.key}
          className={`rounded-sm px-2.5 py-1 text-xs font-medium transition ${
            value === option.key ? "bg-primary-500 text-white" : "text-ink-500 hover:text-ink-800"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}


function QueryDetail({ log }: { log: QueryLog | null }) {
  if (!log) {
    return (
      <div className="rounded-lg border border-dashed border-ink-200 bg-white px-4 py-12">
        <EmptyState title="Select a query" description="Pick a row to inspect retrieved chunks, citations, and timing." />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <section className="rounded-lg border border-ink-100 bg-white p-4">
        <header className="mb-3 flex items-center justify-between">
          <Badge tone={log.status === "ok" ? "success" : "danger"}>{log.status}</Badge>
          <span className="text-xs font-mono text-ink-400">{log.id.slice(0, 8)}</span>
        </header>
        <p className="whitespace-pre-wrap text-sm text-ink-800">{log.question}</p>
        <p className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-500">
          <span>{log.endpoint}</span>
          <span>·</span>
          <span>{log.embedding_provider ?? "—"}</span>
          {log.answer_model ? (
            <>
              <span>·</span>
              <span>{log.answer_model}</span>
            </>
          ) : null}
          <span>·</span>
          <span>top-{log.top_k}</span>
          <span>·</span>
          <span>{log.latency_ms ?? "?"} ms</span>
          {log.token_usage ? (
            <>
              <span>·</span>
              <span className="tabular-nums">
                {Object.entries(log.token_usage)
                  .map(([key, value]) => `${key.replace("_tokens", "")} ${value}`)
                  .join(" · ")}
              </span>
            </>
          ) : null}
        </p>
      </section>

      {log.error ? (
        <Banner tone="danger">
          <span className="font-mono text-xs">{log.error}</span>
        </Banner>
      ) : null}

      {log.retrieved_chunk_ids.length > 0 ? (
        <section className="rounded-lg border border-ink-100 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold text-ink-800">Retrieved</h2>
          <ol className="space-y-1.5">
            {log.retrieved_chunk_ids.map((chunkId, index) => (
              <li key={chunkId} className="flex items-center justify-between gap-3 text-sm">
                <span className="truncate text-ink-700">
                  <span className="text-ink-400">{index + 1}.</span>{" "}
                  {log.retrieved_documents[index] ?? chunkId.slice(0, 8)}
                </span>
                <span className="shrink-0 tabular-nums text-xs text-ink-400">
                  {(log.retrieved_scores[index] ?? 0).toFixed(3)}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {log.citations.length > 0 ? (
        <section className="rounded-lg border border-ink-100 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold text-ink-800">Citations</h2>
          <ol className="space-y-1.5 text-sm text-ink-700">
            {log.citations.map((citation, index) => (
              <li key={citation.chunk_id} className="flex items-center gap-2">
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-ink-300 bg-white px-1 text-[11px] font-semibold">
                  {index + 1}
                </span>
                {citation.source_filename}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}


function confidenceTone(confidence: string): "success" | "warning" | "danger" | "neutral" {
  if (confidence === "high") return "success";
  if (confidence === "medium") return "warning";
  if (confidence === "low") return "danger";
  return "neutral";
}


function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
  }).format(new Date(value));
}
