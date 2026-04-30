"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import type { EvalRunDetail, EvalRunSummary, RetrievalMode } from "@/lib/types";


export function EvalsDashboard() {
  const [runs, setRuns] = useState<EvalRunSummary[]>([]);
  const [selected, setSelected] = useState<EvalRunDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoadingList(true);
    try {
      setRuns(await api.listEvals());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load runs.");
    } finally {
      setLoadingList(false);
    }
  }

  async function openRun(runId: string) {
    setLoadingDetail(true);
    try {
      const detail = await api.getEval(runId);
      setSelected(detail);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load run.");
    } finally {
      setLoadingDetail(false);
    }
  }

  async function triggerRun(mode: RetrievalMode) {
    setRunning(true);
    setError(null);
    try {
      await api.runEval({ retrieval_mode: mode, name: `${mode}-${new Date().toISOString().slice(0, 16)}` });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Run failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ink-900">Evals</h1>
          <p className="mt-1 text-sm text-ink-500">
            Per-run retrieval and groundedness metrics from the eval harness.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/evals/compare" className="text-sm text-ink-500 hover:text-ink-900">
            Compare runs →
          </Link>
          <Button variant="secondary" onClick={() => triggerRun("dense")} disabled={running}>
            {running ? "Running…" : "Run dense"}
          </Button>
          <Button onClick={() => triggerRun("hybrid")} disabled={running}>
            {running ? "Running…" : "Run hybrid"}
          </Button>
        </div>
      </header>

      {error ? <Banner tone="danger" className="mb-3">{error}</Banner> : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <RunsList runs={runs} loading={loadingList} selectedId={selected?.id ?? null} onSelect={openRun} />
        <RunDetail detail={selected} loading={loadingDetail} />
      </div>
    </div>
  );
}


function RunsList({
  runs,
  loading,
  selectedId,
  onSelect,
}: {
  runs: EvalRunSummary[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (runId: string) => void;
}) {
  if (loading && runs.length === 0) {
    return (
      <div className="rounded-lg border border-ink-100 bg-white p-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="my-2 h-14 animate-pulse rounded-md bg-ink-50" />
        ))}
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="rounded-lg border border-ink-100 bg-white px-4 py-12">
        <EmptyState
          title="No eval runs yet"
          description="Trigger a hybrid or dense run to populate this list. Re-running with the same config produces the same config_hash."
        />
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-ink-100 bg-white">
      <ol className="divide-y divide-ink-100">
        {runs.map((run) => (
          <li key={run.id}>
            <button
              type="button"
              onClick={() => onSelect(run.id)}
              className={`flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition ${
                selectedId === run.id ? "bg-ink-50" : "hover:bg-ink-50/60"
              }`}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink-900">{run.name ?? run.id.slice(0, 8)}</p>
                <p className="mt-0.5 text-xs text-ink-500">
                  {formatDate(run.started_at)} · {String(run.config_snapshot.retrieval_mode ?? "—")} ·{" "}
                  config <span className="font-mono">{run.config_hash.slice(0, 8)}</span>
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <Badge tone={run.status === "completed" ? "success" : run.status === "failed" ? "danger" : "warning"}>
                  {run.status}
                </Badge>
                <p className="text-xs tabular-nums text-ink-500">
                  R@k {formatMetric(run.aggregate_metrics.recall_at_k_mean)} · MRR{" "}
                  {formatMetric(run.aggregate_metrics.mrr_mean)}
                </p>
              </div>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}


function RunDetail({ detail, loading }: { detail: EvalRunDetail | null; loading: boolean }) {
  if (loading) {
    return (
      <div className="rounded-lg border border-ink-100 bg-white p-3">
        <div className="my-2 h-32 animate-pulse rounded-md bg-ink-50" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="rounded-lg border border-dashed border-ink-200 bg-white px-4 py-12">
        <EmptyState title="Select a run" description="Pick a run on the left to inspect per-case metrics." />
      </div>
    );
  }

  const aggregate = detail.aggregate_metrics ?? {};

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-ink-100 bg-white p-4">
        <header className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="font-medium text-ink-900">{detail.name ?? detail.id.slice(0, 8)}</h2>
            <p className="text-xs text-ink-500">
              {String(detail.config_snapshot.retrieval_mode ?? "—")} · top-{String(detail.config_snapshot.top_k ?? "?")} ·{" "}
              <span className="font-mono">{detail.config_hash.slice(0, 12)}</span>
            </p>
          </div>
          <Badge tone={detail.status === "completed" ? "success" : detail.status === "failed" ? "danger" : "warning"}>
            {detail.status}
          </Badge>
        </header>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
          <Metric label="Cases" value={`${detail.completed_cases}/${detail.total_cases}`} />
          <Metric label="Recall@k" value={formatMetric(aggregate.recall_at_k_mean)} />
          <Metric label="MRR" value={formatMetric(aggregate.mrr_mean)} />
          <Metric label="Citation correctness" value={formatMetric(aggregate.citation_correctness_mean)} />
          <Metric label="Abstain accuracy" value={formatMetric(aggregate.abstain_accuracy)} />
          <Metric label="Judge score (1-5)" value={formatMetric(aggregate.judge_score_mean)} />
        </dl>
      </section>

      <section className="overflow-hidden rounded-lg border border-ink-100 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-ink-50/60 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Case</th>
              <th className="px-4 py-2 text-left font-medium">Category</th>
              <th className="px-4 py-2 text-right font-medium">R@k</th>
              <th className="px-4 py-2 text-right font-medium">MRR</th>
              <th className="px-4 py-2 text-right font-medium">Cite</th>
              <th className="px-4 py-2 text-center font-medium">Abstain</th>
              <th className="px-4 py-2 text-right font-medium">Judge</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {detail.cases.map((row) => (
              <tr key={row.id} className="hover:bg-ink-50/50">
                <td className="px-4 py-2">
                  <p className="truncate font-medium text-ink-900">{row.case_id}</p>
                  <p className="truncate text-xs text-ink-500">{row.question}</p>
                </td>
                <td className="px-4 py-2 text-ink-600">{row.category ?? "—"}</td>
                <td className="px-4 py-2 text-right tabular-nums text-ink-700">
                  {formatMetric(numberOrNull(row.metrics.recall_at_k))}
                </td>
                <td className="px-4 py-2 text-right tabular-nums text-ink-700">
                  {formatMetric(numberOrNull(row.metrics.mrr))}
                </td>
                <td className="px-4 py-2 text-right tabular-nums text-ink-700">
                  {formatMetric(numberOrNull(row.metrics.citation_correctness))}
                </td>
                <td className="px-4 py-2 text-center">
                  {row.metrics.abstain_correct === true ? (
                    <span className="text-emerald-700">✓</span>
                  ) : row.metrics.abstain_correct === false ? (
                    <span className="text-rose-700">✗</span>
                  ) : (
                    <span className="text-ink-400">—</span>
                  )}
                </td>
                <td className="px-4 py-2 text-right tabular-nums text-ink-700">
                  {row.judge?.score != null ? row.judge.score : <span className="text-ink-400">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}


function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className="font-display text-lg font-semibold tabular-nums text-ink-900">{value}</dd>
    </div>
  );
}


function formatMetric(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(3);
}


function numberOrNull(value: number | boolean | null | undefined): number | null {
  return typeof value === "number" ? value : null;
}


function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
  }).format(new Date(value));
}
