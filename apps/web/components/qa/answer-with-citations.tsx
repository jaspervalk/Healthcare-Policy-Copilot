import { Children, isValidElement, type ReactNode } from "react";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { AnswerCitation } from "@/lib/types";

import { CitationChip } from "./citation-chip";


/**
 * Render the model's answer as markdown, with inline `[N]` citation markers
 * replaced by interactive citation chips.
 *
 * The model emits markdown text that already contains the markers (e.g.
 * `coverage requires medical necessity [1]`). We let react-markdown parse the
 * structure (paragraphs, lists, bold, italic) and walk every text leaf,
 * splitting on `[N]` patterns and substituting a `CitationChip` for each
 * recognized marker. Unknown numbers (e.g. `[7]` when only 3 citations exist)
 * pass through as plain text — we don't want to fail loudly on a model slip.
 */
export function AnswerWithCitations({
  answer,
  citations,
  selectedChunkId,
  onCitationClick,
}: {
  answer: string;
  citations: AnswerCitation[];
  selectedChunkId: string | null;
  onCitationClick: (chunkId: string) => void;
}) {
  // We split the text on bracket patterns and resolve each bracket against the
  // citations list. The model may emit either form:
  //   [1]                                        — 1-indexed ordinal
  //   [4abde88e-71bb-475e-a752-b159f75c8158]     — chunk_id (UUID)
  //   [1, 2] or [uuid; uuid]                     — multiple citations
  // Unresolvable brackets pass through as plain text — we never fail loud on a
  // model slip.
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const citationByChunkId = new Map(
    citations.map((citation, index) => [citation.chunk_id, { citation, oneBased: index + 1 }]),
  );

  type Resolved = { citation: AnswerCitation; oneBased: number };

  function resolveBracket(inner: string): Resolved[] | null {
    const trimmed = inner.trim();
    if (!trimmed) return null;
    const parts = trimmed.split(/[,;]\s*/);
    const resolved: Resolved[] = [];
    for (const part of parts) {
      const token = part.trim();
      const numericMatch = /^\d+$/.exec(token);
      if (numericMatch) {
        const oneBased = Number(numericMatch[0]);
        const citation = citations[oneBased - 1];
        if (!citation) return null;
        resolved.push({ citation, oneBased });
        continue;
      }
      if (UUID_RE.test(token)) {
        const hit = citationByChunkId.get(token);
        if (!hit) return null;
        resolved.push(hit);
        continue;
      }
      return null;
    }
    return resolved.length > 0 ? resolved : null;
  }

  function injectChips(text: string): ReactNode[] {
    // Capturing group means split() interleaves matched brackets between text.
    // Even indices are surrounding text; odd indices are `[...]` matches.
    const segments = text.split(/(\[[^\]]+\])/g);
    const out: ReactNode[] = [];
    let keyCounter = 0;
    for (let i = 0; i < segments.length; i += 1) {
      const segment = segments[i];
      if (i % 2 === 0) {
        if (segment) out.push(segment);
        continue;
      }
      const resolved = resolveBracket(segment.slice(1, -1));
      if (!resolved) {
        out.push(segment);
        continue;
      }
      // Deduplicate within a single bracket (e.g. [1, 1, 2] → [1, 2]).
      const seen = new Set<string>();
      for (const { citation, oneBased } of resolved) {
        if (seen.has(citation.chunk_id)) continue;
        seen.add(citation.chunk_id);
        out.push(
          <CitationChip
            key={`chip-${keyCounter++}-${citation.chunk_id}`}
            citation={citation}
            number={oneBased}
            active={selectedChunkId === citation.chunk_id}
            onClick={() => onCitationClick(citation.chunk_id)}
          />,
        );
      }
    }
    return out;
  }

  function transformChildren(children: ReactNode): ReactNode {
    return Children.map(children, (child) => {
      if (typeof child === "string") {
        return injectChips(child);
      }
      if (isValidElement(child)) {
        const props = child.props as { children?: ReactNode };
        if (props.children !== undefined) {
          return {
            ...child,
            props: { ...props, children: transformChildren(props.children) },
          };
        }
      }
      return child;
    });
  }

  return (
    <div className="prose-answer font-sans text-[15px] leading-7 text-ink-800">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-3 last:mb-0">{transformChildren(children)}</p>,
          ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li>{transformChildren(children)}</li>,
          strong: ({ children }) => <strong className="font-semibold text-ink-900">{transformChildren(children)}</strong>,
          em: ({ children }) => <em className="italic">{transformChildren(children)}</em>,
          h1: ({ children }) => <h3 className="mb-2 mt-4 font-display text-lg font-semibold text-ink-900 first:mt-0">{transformChildren(children)}</h3>,
          h2: ({ children }) => <h3 className="mb-2 mt-4 font-display text-base font-semibold text-ink-900 first:mt-0">{transformChildren(children)}</h3>,
          h3: ({ children }) => <h4 className="mb-2 mt-3 font-semibold text-ink-900 first:mt-0">{transformChildren(children)}</h4>,
          code: ({ children }) => <code className="rounded bg-ink-100 px-1 py-0.5 font-mono text-[13px] text-ink-800">{children}</code>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-primary-600 underline hover:text-primary-500">
              {transformChildren(children)}
            </a>
          ),
        }}
      >
        {answer}
      </ReactMarkdown>
    </div>
  );
}
