"use client";

import { useEffect, useMemo, useState } from "react";

import { Banner } from "@/components/ui/banner";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import type { AnswerResult, DocumentItem, QueryFilters, RetrievalMode } from "@/lib/types";

import { AnswerWithCitations } from "./answer-with-citations";
import { Composer } from "./composer";
import { ConfidenceChip } from "./confidence-chip";
import { EvidencePanel } from "./evidence-panel";


const SAMPLE_QUESTIONS = [
  "What is the urgent prior authorization escalation process?",
  "How many days does a Medicare benefit period cover for inpatient hospital services?",
  "Which services are excluded from inpatient psychiatric hospital coverage?",
];


export function QaWorkspace() {
  const [question, setQuestion] = useState("");
  const [filters, setFilters] = useState<QueryFilters>({});
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("hybrid");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const indexedCount = useMemo(
    () => documents.filter((document) => document.ingestion_status === "indexed").length,
    [documents],
  );

  useEffect(() => {
    void (async () => {
      try {
        const list = await api.listDocuments();
        setDocuments(list);
      } catch {
        // Library state is best-effort; we don't surface this as a blocking error.
      }
    })();
  }, []);

  const filterOptions = useMemo(() => {
    const collect = (key: keyof DocumentItem) =>
      Array.from(
        new Set(documents.map((document) => document[key]).filter((value): value is string => Boolean(value))),
      ).sort();
    return {
      department: collect("department"),
      document_type: collect("document_type"),
      policy_status: collect("policy_status"),
    };
  }, [documents]);

  async function handleSubmit() {
    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await api.answer({
        question: trimmed,
        filters,
        retrieval_mode: retrievalMode,
      });
      setResult(response);
      setSelectedChunkId(response.citations[0]?.chunk_id ?? response.retrieved_chunks[0]?.chunk_id ?? null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Answer generation failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-6">
        <h1 className="font-display text-2xl font-semibold tracking-tight text-ink-900">Ask</h1>
        <p className="mt-1 text-sm text-ink-500">
          Grounded answers over {indexedCount} indexed document{indexedCount === 1 ? "" : "s"}.
        </p>
      </header>

      <Composer
        question={question}
        onQuestionChange={setQuestion}
        filters={filters}
        onFiltersChange={setFilters}
        retrievalMode={retrievalMode}
        onRetrievalModeChange={setRetrievalMode}
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        disabled={!question.trim() || indexedCount === 0}
        filterOptions={filterOptions}
      />

      {error ? <Banner tone="danger" className="mt-4">{error}</Banner> : null}

      {!result && indexedCount === 0 ? (
        <div className="mt-12">
          <EmptyState
            title="No indexed documents yet"
            description="Upload a PDF on the Library page to give the system something to ground against."
          />
        </div>
      ) : null}

      {!result && indexedCount > 0 ? (
        <div className="mt-8">
          <p className="text-xs uppercase tracking-wide text-ink-400">Try a question</p>
          <ul className="mt-2 space-y-1.5">
            {SAMPLE_QUESTIONS.map((sample) => (
              <li key={sample}>
                <button
                  type="button"
                  onClick={() => setQuestion(sample)}
                  className="text-left text-sm text-ink-600 hover:text-ink-900"
                >
                  {sample}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {result ? (
        <AnswerView
          result={result}
          selectedChunkId={selectedChunkId}
          onSelect={setSelectedChunkId}
        />
      ) : null}
    </div>
  );
}


function AnswerView({
  result,
  selectedChunkId,
  onSelect,
}: {
  result: AnswerResult;
  selectedChunkId: string | null;
  onSelect: (chunkId: string | null) => void;
}) {
  return (
    <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        <div className="rounded-lg border border-ink-100 bg-white p-5 shadow-soft">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <ConfidenceChip
              confidence={result.confidence}
              reasons={result.confidence_reasons}
              inputs={result.confidence_inputs}
            />
            {result.abstained ? (
              <span className="inline-flex h-7 items-center rounded-md border border-amber-200 bg-amber-50 px-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
                abstained
              </span>
            ) : null}
          </div>
          <AnswerWithCitations
            answer={result.answer}
            citations={result.citations}
            selectedChunkId={selectedChunkId}
            onCitationClick={onSelect}
          />
          <AnswerMeta result={result} />
        </div>
      </div>
      <aside className="lg:sticky lg:top-20 lg:self-start">
        <EvidencePanel
          citations={result.citations}
          retrievedChunks={result.retrieved_chunks}
          selectedChunkId={selectedChunkId}
          onSelect={onSelect}
        />
      </aside>
    </div>
  );
}


function AnswerMeta({ result }: { result: AnswerResult }) {
  const tokenSummary = result.token_usage
    ? Object.entries(result.token_usage)
        .filter(([, value]) => typeof value === "number")
        .map(([key, value]) => `${key.replace("_tokens", "")} ${value}`)
        .join(" · ")
    : null;

  return (
    <p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-400">
      <span>{result.answer_model}</span>
      <span>·</span>
      <span>{result.embedding_provider}</span>
      <span>·</span>
      <span>top-{result.top_k}</span>
      {tokenSummary ? (
        <>
          <span>·</span>
          <span className="tabular-nums">{tokenSummary}</span>
        </>
      ) : null}
    </p>
  );
}
