"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Banner } from "@/components/ui/banner";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import type {
  AnswerResult,
  DocumentItem,
  QueryFilters,
  RetrievalMode,
  RetrievedChunk,
} from "@/lib/types";

import { AbstainNotice } from "./abstain-notice";
import { AnswerWithCitations } from "./answer-with-citations";
import { Composer } from "./composer";
import { ConfidenceChip } from "./confidence-chip";
import { EvidencePanel } from "./evidence-panel";


const SAMPLE_QUESTIONS = [
  "Wanneer worden de salarissen volgens de CAO GGZ verhoogd en met welk percentage?",
  "Hoeveel vakantie-uren heeft een fulltime medewerker per jaar volgens de CAO GGZ?",
  "Wat is de vergoeding voor consignatiediensten en bereikbaarheidsdiensten?",
];


type Stage = "idle" | "retrieving" | "composing" | "done" | "error";


type StreamingState = {
  stage: Stage;
  retrievedChunks: RetrievedChunk[];
  embeddingProvider: string | null;
  partialAnswer: string;
  result: AnswerResult | null;
  error: string | null;
};


const initialStreamingState: StreamingState = {
  stage: "idle",
  retrievedChunks: [],
  embeddingProvider: null,
  partialAnswer: "",
  result: null,
  error: null,
};


export function QaWorkspace() {
  const [question, setQuestion] = useState("");
  const [filters, setFilters] = useState<QueryFilters>({});
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("hybrid");
  const [streamingState, setStreamingState] = useState<StreamingState>(initialStreamingState);
  const [selectedChunkId, setSelectedChunkId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

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

  // ⌘K / Ctrl+K → focus composer.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        composerRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
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

  async function runQuestion(text: string, source: "manual" | "suggestion" = "manual") {
    const trimmed = text.trim();
    if (!trimmed) return;

    setStreamingState({ ...initialStreamingState, stage: "retrieving" });
    setSelectedChunkId(null);

    await api.streamAnswer(
      {
        question: trimmed,
        filters,
        retrieval_mode: retrievalMode,
        source,
      },
      {
        onRetrieval: (payload) => {
          setStreamingState((current) => ({
            ...current,
            stage: "composing",
            embeddingProvider: payload.embedding_provider,
            retrievedChunks: payload.retrieved_chunks,
            partialAnswer: "",
          }));
        },
        onAnswerDelta: (delta) => {
          setStreamingState((current) => ({
            ...current,
            partialAnswer: current.partialAnswer + delta,
          }));
        },
        onComplete: (result) => {
          setStreamingState({
            stage: "done",
            embeddingProvider: result.embedding_provider,
            retrievedChunks: result.retrieved_chunks,
            partialAnswer: result.answer,
            result,
            error: null,
          });
          setSelectedChunkId(
            result.citations[0]?.chunk_id ?? result.retrieved_chunks[0]?.chunk_id ?? null,
          );
        },
        onError: (message) => {
          setStreamingState((current) => ({
            ...current,
            stage: "error",
            error: message,
          }));
        },
      },
    );
  }

  async function handleSubmit() {
    await runQuestion(question);
  }

  function handleSuggestionClick(text: string) {
    setQuestion(text);
    void runQuestion(text, "suggestion");
  }

  const isStreaming = streamingState.stage === "retrieving" || streamingState.stage === "composing";

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ink-900">Ask</h1>
          <p className="mt-1 text-sm text-ink-500">
            Grounded answers over {indexedCount} indexed document{indexedCount === 1 ? "" : "s"}.
          </p>
        </div>
        <kbd className="hidden items-center gap-1 rounded-md border border-ink-200 bg-white px-1.5 py-0.5 text-[11px] font-medium text-ink-500 md:inline-flex">
          <span>⌘</span>K
          <span className="ml-1 text-ink-400">to focus</span>
        </kbd>
      </header>

      <Composer
        ref={composerRef}
        question={question}
        onQuestionChange={setQuestion}
        filters={filters}
        onFiltersChange={setFilters}
        retrievalMode={retrievalMode}
        onRetrievalModeChange={setRetrievalMode}
        onSubmit={handleSubmit}
        isSubmitting={isStreaming}
        disabled={!question.trim() || indexedCount === 0}
        filterOptions={filterOptions}
      />

      {streamingState.error ? (
        <Banner tone="danger" className="mt-4">{streamingState.error}</Banner>
      ) : null}

      {streamingState.stage === "idle" && indexedCount === 0 ? (
        <div className="mt-12">
          <EmptyState
            title="No indexed documents yet"
            description="Upload a PDF on the Library page to give the system something to ground against."
          />
        </div>
      ) : null}

      {streamingState.stage === "idle" && indexedCount > 0 ? (
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

      {streamingState.stage !== "idle" && streamingState.stage !== "error" ? (
        <StreamingView
          state={streamingState}
          selectedChunkId={selectedChunkId}
          onSelect={setSelectedChunkId}
          onSuggestionClick={handleSuggestionClick}
        />
      ) : null}
    </div>
  );
}


function StreamingView({
  state,
  selectedChunkId,
  onSelect,
  onSuggestionClick,
}: {
  state: StreamingState;
  selectedChunkId: string | null;
  onSelect: (chunkId: string | null) => void;
  onSuggestionClick: (text: string) => void;
}) {
  const { stage, result, retrievedChunks } = state;
  const showAnswerCard = stage === "composing" || (stage === "done" && result !== null);

  return (
    <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        {showAnswerCard ? (
          <div className="rounded-lg border border-ink-100 bg-white p-5 shadow-soft">
            {stage === "composing" ? (
              <StreamingAnswer partialAnswer={state.partialAnswer} />
            ) : result ? (
              <>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <ConfidenceChip
                    confidence={result.confidence}
                    reasons={result.confidence_reasons}
                    inputs={result.confidence_inputs}
                  />
                </div>
                {result.abstained ? (
                  <AbstainNotice result={result} />
                ) : (
                  <AnswerWithCitations
                    answer={result.answer}
                    citations={result.citations}
                    selectedChunkId={selectedChunkId}
                    onCitationClick={onSelect}
                  />
                )}
                {result.suggested_questions && result.suggested_questions.length > 0 ? (
                  <SuggestedQuestions
                    questions={result.suggested_questions}
                    onClick={onSuggestionClick}
                  />
                ) : null}
                <AnswerMeta result={result} />
              </>
            ) : null}
          </div>
        ) : (
          <RetrievalSkeleton />
        )}
      </div>

      <aside className="lg:sticky lg:top-20 lg:self-start">
        {retrievedChunks.length > 0 ? (
          <EvidencePanel
            citations={result?.citations ?? []}
            retrievedChunks={retrievedChunks}
            selectedChunkId={selectedChunkId}
            onSelect={onSelect}
          />
        ) : (
          <EvidenceSkeleton />
        )}
      </aside>
    </div>
  );
}


function RetrievalSkeleton() {
  return (
    <div className="rounded-lg border border-ink-100 bg-white p-5 shadow-soft">
      <p className="flex items-center gap-2 text-sm text-ink-500">
        <Spinner /> Retrieving evidence…
      </p>
    </div>
  );
}


function StreamingAnswer({ partialAnswer }: { partialAnswer: string }) {
  if (!partialAnswer) {
    return (
      <div className="space-y-3">
        <p className="flex items-center gap-2 text-sm text-ink-500">
          <Spinner /> Generating answer…
        </p>
        <div className="space-y-2">
          <div className="h-3 animate-pulse rounded bg-ink-100" />
          <div className="h-3 w-11/12 animate-pulse rounded bg-ink-100" />
          <div className="h-3 w-9/12 animate-pulse rounded bg-ink-100" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-xs text-ink-400">
        <Spinner /> Streaming…
      </p>
      <p className="whitespace-pre-wrap font-sans text-[15px] leading-7 text-ink-800">
        {partialAnswer}
        <span
          aria-hidden
          className="ml-0.5 inline-block h-4 w-[1px] -translate-y-[1px] animate-pulse bg-ink-500 align-middle"
        />
      </p>
    </div>
  );
}


function EvidenceSkeleton() {
  return (
    <div className="rounded-lg border border-ink-100 bg-white">
      <div className="border-b border-ink-100 px-4 py-2.5">
        <span className="text-sm font-semibold text-ink-800">Evidence</span>
      </div>
      <div className="space-y-2 p-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="h-12 animate-pulse rounded bg-ink-50" />
        ))}
      </div>
    </div>
  );
}


function Spinner() {
  return (
    <svg className="h-3.5 w-3.5 animate-spin text-ink-400" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
      <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}


function SuggestedQuestions({
  questions,
  onClick,
}: {
  questions: string[];
  onClick: (text: string) => void;
}) {
  return (
    <div className="mt-5 border-t border-ink-100 pt-4">
      <p className="text-[11px] font-medium uppercase tracking-wide text-ink-400">
        Try a follow-up
      </p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {questions.map((text) => (
          <li key={text}>
            <button
              type="button"
              onClick={() => onClick(text)}
              className="rounded-full border border-ink-200 bg-white px-3 py-1 text-xs text-ink-700 transition hover:border-primary-400 hover:bg-primary-50 hover:text-primary-700"
            >
              {text}
            </button>
          </li>
        ))}
      </ul>
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
