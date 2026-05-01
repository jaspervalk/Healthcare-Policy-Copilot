"use client";

import { useState } from "react";

import type { AnswerCitation } from "@/lib/types";


/**
 * Inline `[N]` citation marker. Hovering reveals a floating preview card with
 * the cited chunk's source, page range, score, and quote preview — so a viewer
 * can read the evidence without leaving the answer.
 *
 * Clicking the marker calls `onClick` (the parent uses this to scroll the
 * evidence panel and set the selected chunk).
 */
export function CitationChip({
  citation,
  number,
  active,
  onClick,
}: {
  citation: AnswerCitation;
  number: number;
  active: boolean;
  onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);

  return (
    <span className="relative inline-block align-text-top">
      <button
        type="button"
        onClick={onClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onFocus={() => setHovered(true)}
        onBlur={() => setHovered(false)}
        aria-label={`Citation ${number}: ${citation.document_title}, pages ${citation.page_start}-${citation.page_end}`}
        className={`mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-sm border px-1 text-[11px] font-semibold transition ${
          active
            ? "border-primary-500 bg-primary-500 text-white"
            : "border-ink-300 bg-white text-ink-700 hover:border-primary-500 hover:text-primary-600"
        }`}
      >
        {number}
      </button>
      {hovered ? (
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-1/2 z-30 mb-2 w-80 -translate-x-1/2 rounded-md border border-ink-200 bg-white p-3 text-left shadow-lift"
        >
          <span className="block text-[11px] font-medium uppercase tracking-wide text-ink-400">
            Citation {number} · score {citation.score > 0 ? citation.score.toFixed(2) : "—"}
          </span>
          <span className="mt-1 block truncate text-sm font-semibold text-ink-900">
            {citation.document_title}
          </span>
          <span className="block text-xs text-ink-500">
            {citation.section_path ?? "general section"} · pages {citation.page_start}-{citation.page_end}
          </span>
          <span className="mt-2 block text-xs leading-5 text-ink-700">
            {citation.quote_preview}
          </span>
        </span>
      ) : null}
    </span>
  );
}
