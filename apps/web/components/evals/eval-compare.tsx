"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import type { EvalCase, EvalRunDetail, EvalRunSummary } from "@/lib/types";


type MetricKey = "recall_at_k" | "mrr" | "citation_correctness" | "judge_score";

const METRIC_LABELS: Record<MetricKey, string> = {
  recall_at_k: "R@k",
  mrr: "MRR",
  citation_correctness: "Citation",
  judge_score: "Judge",
};


export function EvalCompare() {
  const [runs, setRuns] = useState<EvalRunSummary[]>([]);
  const [aId, setAId] = useState<string | null>(null);
  const [bId, setBId] = useState<string | null>(null);
  const [aDetail, setADetail] = useState<EvalRunDetail | null>(null);
  const [bDetail, setBDetail] = useState<EvalRunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      const list = await api.listEvals();
      const completed = list.filter((run) => run.status === "completed");
      setRuns(completed);
      if (completed.length >= 2 && !aId && !bId) {
        // Sensible default: latest two completed runs.
        setBId(completed[0].id);
        setAId(completed[1].id);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load runs.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    if (!aId || !bId) {
      setADetail(null);
      setBDetail(null);
      return;
    }
    setLoadingDetail(true);
    setError(null);
    Promise.all([api.getEval(aId), api.getEval(bId)])
      .then(([a, b]) => {
        if (cancelled) return;
        setADetail(a);
        setBDetail(b);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "Failed to load run detail.");
      })
      .finally(() => {
        if (!cancelled) setLoadingDetail(false);
      });
    return () => {
      cancelled = true;
    };
  }, [aId, bId]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ink-900">Compare runs</h1>
          <p className="mt-1 text-sm text-ink-500">
            Joined by <span className="font-mono">case_id</span>. Δ = run B − run A; positive numbers favor B.
          </p>
        </div>
        <Link href="/evals" className="text-sm text-ink-500 hover:text-ink-900">
          ← Back to runs
        </Link>
      </header>

      {error ? <Banner tone="danger" className="mb-3">{error}</Banner> : null}

      <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-2">
        <RunPicker
          label="Run A (baseline)"
          runs={runs}
          loading={loading}
          value={aId}
          onChange={setAId}
          disallow={bId}
        />
        <RunPicker
          label="Run B (compare)"
          runs={runs}
          loading={loading}
          value={bId}
          onChange={setBId}
          disallow={aId}
        />
      </div>

      {!aId || !bId ? (
        <div className="rounded-lg border border-dashed border-ink-200 bg-white px-4 py-12">
          <EmptyState
            title="Pick two runs"
            description={
              runs.length < 2
                ? "Run at least two evals to compare. Try one in dense mode and one in hybrid mode."
                : "Choose a baseline and a comparison run above."
            }
            action={
              runs.length < 2 ? (
                <Link href="/evals">
                  <Button>Go to runs</Button>
                </Link>
              ) : null
            }
          />
        </div>
      ) : loadingDetail || !aDetail || !bDetail ? (
        <div className="rounded-lg border border-ink-100 bg-white p-3">
          <div className="my-2 h-32 animate-pulse rounded-md bg-ink-50" />
          <div className="my-2 h-64 animate-pulse rounded-md bg-ink-50" />
        </div>
      ) : (
        <Comparison a={aDetail} b={bDetail} />
      )}
    </div>
  );
}


function RunPicker({
  label,
  runs,
  loading,
  value,
  onChange,
  disallow,
}: {
  label: string;
  runs: EvalRunSummary[];
  loading: boolean;
  value: string | null;
  onChange: (id: string | null) => void;
  disallow: string | null;
}) {
  return (
    <label className="block rounded-lg border border-ink-100 bg-white px-3 py-2.5">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</span>
      <select
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value || null)}
        disabled={loading}
        className="mt-1 block w-full border-0 bg-transparent text-sm font-medium text-ink-800 focus:outline-none focus:ring-0"
      >
        <option value="">— choose —</option>
        {runs.map((run) => (
          <option key={run.id} value={run.id} disabled={run.id === disallow}>
            {(run.name ?? run.id.slice(0, 8))} · {String(run.config_snapshot.retrieval_mode ?? "?")} · {run.config_hash.slice(0, 8)}
          </option>
        ))}
      </select>
    </label>
  );
}


function Comparison({ a, b }: { a: EvalRunDetail; b: EvalRunDetail }) {
  const aggA = a.aggregate_metrics ?? {};
  const aggB = b.aggregate_metrics ?? {};

  const aggregateRows: { key: string; label: string; a: number | null; b: number | null }[] = [
    { key: "recall_at_k_mean", label: "Recall@k", a: numberOr(aggA.recall_at_k_mean), b: numberOr(aggB.recall_at_k_mean) },
    { key: "mrr_mean", label: "MRR", a: numberOr(aggA.mrr_mean), b: numberOr(aggB.mrr_mean) },
    {
      key: "citation_correctness_mean",
      label: "Citation correctness",
      a: numberOr(aggA.citation_correctness_mean),
      b: numberOr(aggB.citation_correctness_mean),
    },
    {
      key: "abstain_accuracy",
      label: "Abstain accuracy",
      a: numberOr(aggA.abstain_accuracy),
      b: numberOr(aggB.abstain_accuracy),
    },
    {
      key: "judge_score_mean",
      label: "Judge (1-5)",
      a: numberOr(aggA.judge_score_mean),
      b: numberOr(aggB.judge_score_mean),
    },
  ];

  const cases = useMemo(() => joinCases(a.cases, b.cases), [a.cases, b.cases]);
  const wins = countWins(cases);
  const sameConfig = a.config_hash === b.config_hash;

  return (
    <div className="space-y-5">
      <section className="grid gap-3 rounded-lg border border-ink-100 bg-white p-4 sm:grid-cols-2">
        <RunHeader detail={a} label="A" />
        <RunHeader detail={b} label="B" />
        {sameConfig ? (
          <div className="sm:col-span-2">
            <Banner tone="warning">
              Both runs share the same <span className="font-mono">config_hash</span>; deltas will reflect run-to-run noise only.
            </Banner>
          </div>
        ) : null}
      </section>

      <section className="overflow-hidden rounded-lg border border-ink-100 bg-white">
        <header className="flex items-center justify-between border-b border-ink-100 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-ink-800">Aggregate</h2>
          <span className="text-xs text-ink-500">
            B wins {wins.bWins} · A wins {wins.aWins} · ties {wins.ties}
          </span>
        </header>
        <table className="w-full text-sm">
          <thead className="bg-ink-50/60 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Metric</th>
              <th className="px-4 py-2 text-right font-medium">A</th>
              <th className="px-4 py-2 text-right font-medium">B</th>
              <th className="px-4 py-2 text-right font-medium">Δ</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {aggregateRows.map((row) => (
              <tr key={row.key}>
                <td className="px-4 py-2 text-ink-700">{row.label}</td>
                <td className="px-4 py-2 text-right tabular-nums text-ink-700">{formatMetric(row.a)}</td>
                <td className="px-4 py-2 text-right tabular-nums text-ink-700">{formatMetric(row.b)}</td>
                <td className="px-4 py-2 text-right tabular-nums">{deltaCell(row.a, row.b)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="overflow-hidden rounded-lg border border-ink-100 bg-white">
        <header className="flex items-center justify-between border-b border-ink-100 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-ink-800">Per case</h2>
          <span className="text-xs text-ink-500">{cases.length} cases</span>
        </header>
        <table className="w-full text-sm">
          <thead className="bg-ink-50/60 text-xs uppercase tracking-wide text-ink-500">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Case</th>
              <th className="px-4 py-2 text-left font-medium">Category</th>
              {(["recall_at_k", "mrr", "citation_correctness", "judge_score"] as MetricKey[]).map((key) => (
                <th key={key} className="px-2 py-2 text-right font-medium" colSpan={3}>
                  {METRIC_LABELS[key]}
                </th>
              ))}
            </tr>
            <tr className="text-[10px] text-ink-400">
              <th className="px-4 pb-2" />
              <th className="px-4 pb-2" />
              {(["recall_at_k", "mrr", "citation_correctness", "judge_score"] as MetricKey[]).flatMap((key) => [
                <th key={`${key}-a`} className="px-1 pb-2 text-right font-medium">A</th>,
                <th key={`${key}-b`} className="px-1 pb-2 text-right font-medium">B</th>,
                <th key={`${key}-d`} className="px-1 pb-2 text-right font-medium">Δ</th>,
              ])}
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {cases.map(({ caseId, a: caseA, b: caseB }) => {
              const question = caseA?.question ?? caseB?.question ?? "—";
              const category = caseA?.category ?? caseB?.category ?? "—";
              return (
                <tr key={caseId} className="hover:bg-ink-50/50">
                  <td className="px-4 py-2">
                    <p className="truncate font-medium text-ink-900">{caseId}</p>
                    <p className="truncate text-xs text-ink-500">{question}</p>
                  </td>
                  <td className="px-4 py-2 text-xs text-ink-600">{category}</td>
                  {(["recall_at_k", "mrr", "citation_correctness", "judge_score"] as MetricKey[]).flatMap((key) => {
                    const av = caseMetric(caseA, key);
                    const bv = caseMetric(caseB, key);
                    return [
                      <td key={`${key}-a`} className="px-1 py-2 text-right tabular-nums text-ink-700">
                        {formatMetric(av)}
                      </td>,
                      <td key={`${key}-b`} className="px-1 py-2 text-right tabular-nums text-ink-700">
                        {formatMetric(bv)}
                      </td>,
                      <td key={`${key}-d`} className="px-1 py-2 text-right tabular-nums">
                        {deltaCell(av, bv)}
                      </td>,
                    ];
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}


function RunHeader({ detail, label }: { detail: EvalRunDetail; label: "A" | "B" }) {
  return (
    <div className="rounded-md border border-ink-100 bg-ink-50/40 p-3">
      <div className="flex items-center justify-between">
        <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-sm bg-ink-800 px-1.5 text-xs font-semibold text-surface">
          {label}
        </span>
        <Badge tone="success">{detail.status}</Badge>
      </div>
      <p className="mt-2 text-sm font-medium text-ink-900">{detail.name ?? detail.id.slice(0, 8)}</p>
      <p className="mt-0.5 text-xs text-ink-500">
        {String(detail.config_snapshot.retrieval_mode ?? "—")} · top-{String(detail.config_snapshot.top_k ?? "?")} ·{" "}
        <span className="font-mono">{detail.config_hash.slice(0, 12)}</span>
      </p>
    </div>
  );
}


type CasePair = { caseId: string; a: EvalCase | null; b: EvalCase | null };

function joinCases(a: EvalCase[], b: EvalCase[]): CasePair[] {
  const byId = new Map<string, CasePair>();
  for (const row of a) {
    byId.set(row.case_id, { caseId: row.case_id, a: row, b: null });
  }
  for (const row of b) {
    const existing = byId.get(row.case_id) ?? { caseId: row.case_id, a: null, b: null };
    existing.b = row;
    byId.set(row.case_id, existing);
  }
  return Array.from(byId.values()).sort((x, y) => x.caseId.localeCompare(y.caseId));
}


function caseMetric(row: EvalCase | null, key: MetricKey): number | null {
  if (!row) return null;
  if (key === "judge_score") {
    return typeof row.judge?.score === "number" ? row.judge.score : null;
  }
  const value = row.metrics[key];
  return typeof value === "number" ? value : null;
}


function countWins(pairs: CasePair[]) {
  let aWins = 0;
  let bWins = 0;
  let ties = 0;
  for (const pair of pairs) {
    const av = caseMetric(pair.a, "recall_at_k");
    const bv = caseMetric(pair.b, "recall_at_k");
    if (av === null || bv === null) continue;
    if (bv > av) bWins += 1;
    else if (av > bv) aWins += 1;
    else ties += 1;
  }
  return { aWins, bWins, ties };
}


function numberOr(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}


function formatMetric(value: number | null): string {
  if (value === null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(3);
}


function deltaCell(a: number | null, b: number | null) {
  if (a === null || b === null) {
    return <span className="text-ink-400">—</span>;
  }
  const delta = b - a;
  if (Math.abs(delta) < 0.0005) {
    return <span className="text-ink-400">0</span>;
  }
  const sign = delta > 0 ? "+" : "";
  const className =
    delta > 0 ? "text-emerald-700" : "text-rose-700";
  return (
    <span className={className}>
      {sign}
      {delta.toFixed(3)}
    </span>
  );
}
