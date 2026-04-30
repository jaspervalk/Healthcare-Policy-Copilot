"use client";

import { useState } from "react";

import type { ConfidenceInputs } from "@/lib/types";


type Confidence = "high" | "medium" | "low";

const toneClasses: Record<Confidence, string> = {
  high: "border-emerald-200 bg-emerald-50 text-emerald-800",
  medium: "border-amber-200 bg-amber-50 text-amber-800",
  low: "border-rose-200 bg-rose-50 text-rose-800",
};


export function ConfidenceChip({
  confidence,
  reasons,
  inputs,
}: {
  confidence: Confidence;
  reasons: string[];
  inputs: ConfidenceInputs | null;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="inline-flex flex-col items-start gap-2">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        className={`inline-flex h-7 items-center gap-1.5 rounded-md border px-2 text-xs font-semibold uppercase tracking-wide ${toneClasses[confidence]}`}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${confidence === "high" ? "bg-emerald-500" : confidence === "medium" ? "bg-amber-500" : "bg-rose-500"}`} />
        {confidence} confidence
        <svg
          className={`h-3 w-3 transition ${expanded ? "rotate-180" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 011.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" />
        </svg>
      </button>
      {expanded ? (
        <div className="rounded-md border border-ink-200 bg-white p-3 text-xs text-ink-700 shadow-soft">
          {inputs ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5">
              <Field label="Top score" value={inputs.top_score.toFixed(3)} />
              <Field label="Score margin" value={inputs.score_margin.toFixed(3)} />
              <Field label="Citations" value={String(inputs.citation_count)} />
              <Field label="Source documents" value={String(inputs.unique_documents)} />
              <Field label="All cited active" value={inputs.all_cited_active ? "yes" : "no"} />
              <Field label="Evidence bucket" value={inputs.evidence_bucket} />
            </dl>
          ) : null}
          {reasons.length ? (
            <ul className="mt-3 list-disc space-y-1 pl-4 text-ink-600">
              {reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}


function Field({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-ink-400">{label}</dt>
      <dd className="font-medium text-ink-800">{value}</dd>
    </>
  );
}
