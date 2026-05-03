"use client";

import { forwardRef, useEffect, useRef, type ReactNode } from "react";

import type { AnswerCitation, RetrievedChunk } from "@/lib/types";


type EvidenceItem = {
  chunk: RetrievedChunk;
  citation: AnswerCitation | null;
  citationNumber: number | null;
};


export function EvidencePanel({
  citations,
  retrievedChunks,
  selectedChunkId,
  onSelect,
}: {
  citations: AnswerCitation[];
  retrievedChunks: RetrievedChunk[];
  selectedChunkId: string | null;
  onSelect: (chunkId: string | null) => void;
}) {
  const items = mergeEvidence(citations, retrievedChunks);
  const selectedRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (selectedChunkId && selectedRef.current) {
      selectedRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [selectedChunkId]);

  if (!items.length) {
    return null;
  }

  return (
    <section aria-label="Retrieved evidence" className="rounded-lg border border-ink-100 bg-white">
      <header className="flex items-center justify-between border-b border-ink-100 px-4 py-2.5">
        <h2 className="text-sm font-semibold text-ink-800">Evidence</h2>
        <span className="text-xs text-ink-400">
          {items.length} chunk{items.length === 1 ? "" : "s"}
        </span>
      </header>
      <ol className="divide-y divide-ink-100">
        {items.map((item) => {
          const isSelected = selectedChunkId === item.chunk.chunk_id;
          return (
            <li key={item.chunk.chunk_id}>
              <EvidenceRow
                ref={isSelected ? selectedRef : null}
                item={item}
                isSelected={isSelected}
                onSelect={onSelect}
              />
            </li>
          );
        })}
      </ol>
    </section>
  );
}


function mergeEvidence(
  citations: AnswerCitation[],
  retrievedChunks: RetrievedChunk[],
): EvidenceItem[] {
  const citationMap = new Map<string, { citation: AnswerCitation; index: number }>();
  citations.forEach((citation, index) => {
    citationMap.set(citation.chunk_id, { citation, index });
  });

  const seen = new Set<string>();
  const items: EvidenceItem[] = [];

  for (const chunk of retrievedChunks) {
    if (seen.has(chunk.chunk_id)) {
      continue;
    }
    seen.add(chunk.chunk_id);
    const match = citationMap.get(chunk.chunk_id);
    items.push({
      chunk,
      citation: match?.citation ?? null,
      citationNumber: match ? match.index + 1 : null,
    });
  }

  return items;
}


type EvidenceRowProps = {
  item: EvidenceItem;
  isSelected: boolean;
  onSelect: (chunkId: string | null) => void;
};


const EvidenceRow = forwardRef<HTMLDivElement, EvidenceRowProps>(function EvidenceRow(
  { item, isSelected, onSelect },
  ref,
) {
  const { chunk, citation, citationNumber } = item;

  return (
    <div
      ref={ref}
      className={`px-4 py-3 transition ${isSelected ? "bg-ink-50" : "bg-white hover:bg-ink-50/60"}`}
      data-chunk-id={chunk.chunk_id}
    >
      <button
        type="button"
        onClick={() => onSelect(isSelected ? null : chunk.chunk_id)}
        className="flex w-full items-start justify-between gap-4 text-left"
        aria-expanded={isSelected}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {citationNumber !== null ? (
              <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-ink-300 bg-white px-1 text-[11px] font-semibold text-ink-700">
                {citationNumber}
              </span>
            ) : (
              <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-sm border border-dashed border-ink-200 px-1 text-[11px] font-medium text-ink-400">
                ·
              </span>
            )}
            <p className="truncate text-sm font-medium text-ink-800">{chunk.document_title}</p>
          </div>
          <p className="mt-0.5 truncate text-xs text-ink-500">
            {chunk.section_path ?? "general section"} · pages {chunk.page_start}-{chunk.page_end}
            {chunk.policy_status ? ` · ${chunk.policy_status}` : ""}
          </p>
        </div>
        <span className="shrink-0 text-xs tabular-nums text-ink-400">
          {chunk.score > 0 ? chunk.score.toFixed(2) : "—"}
        </span>
      </button>

      {isSelected ? (
        <div className="mt-3 space-y-3 text-sm">
          {citation?.quote ? (
            <blockquote className="border-l-2 border-primary-400 bg-primary-50/40 px-3 py-2 italic text-ink-800">
              “{citation.quote}”
            </blockquote>
          ) : null}
          {citation?.support ? (
            <p className="text-xs text-ink-500">{citation.support}</p>
          ) : null}
          <p className="whitespace-pre-wrap leading-6 text-ink-700">
            {renderHighlighted(chunk.text, citation?.quote ?? null)}
          </p>
          <p className="text-xs text-ink-400">{chunk.source_filename}</p>
        </div>
      ) : null}
    </div>
  );
});


/**
 * Highlight `quote` inside `text` with a `<mark>`. Best-effort: tries an exact
 * case-insensitive match first, then falls back to a whitespace-collapsed
 * match (handles minor formatting differences like double spaces or newlines).
 * If no match is found, the chunk renders without highlighting.
 */
function renderHighlighted(text: string, quote: string | null): ReactNode {
  if (!quote) return text;
  const trimmed = quote.trim().replace(/^[“"']+|[”"']+$/g, "").trim();
  if (!trimmed) return text;

  // 1. Exact (case-insensitive) match.
  const lowerText = text.toLowerCase();
  const lowerQuote = trimmed.toLowerCase();
  const exactIdx = lowerText.indexOf(lowerQuote);
  if (exactIdx >= 0) {
    return (
      <>
        {text.slice(0, exactIdx)}
        <mark className="rounded-sm bg-primary-100 px-0.5 text-ink-900">
          {text.slice(exactIdx, exactIdx + trimmed.length)}
        </mark>
        {text.slice(exactIdx + trimmed.length)}
      </>
    );
  }

  // 2. Whitespace-collapsed match — handles cases where the model normalized
  // multiple spaces / newlines while quoting. We compute a regex that allows
  // any run of whitespace between non-whitespace tokens.
  const tokens = trimmed.split(/\s+/).map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (tokens.length === 0) return text;
  const pattern = new RegExp(tokens.join("\\s+"), "i");
  const match = pattern.exec(text);
  if (match) {
    const start = match.index;
    const end = start + match[0].length;
    return (
      <>
        {text.slice(0, start)}
        <mark className="rounded-sm bg-primary-100 px-0.5 text-ink-900">{text.slice(start, end)}</mark>
        {text.slice(end)}
      </>
    );
  }

  return text;
}
