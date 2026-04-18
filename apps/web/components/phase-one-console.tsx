"use client";

import type { ReactNode } from "react";
import { FormEvent, useEffect, useMemo, useState } from "react";


type DocumentItem = {
  id: string;
  title: string;
  source_filename: string;
  ingestion_status: string;
  document_type: string | null;
  department: string | null;
  policy_status: string | null;
  effective_date: string | null;
  review_date: string | null;
  version_label: string | null;
  page_count: number;
  parse_error: string | null;
  extracted_metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  chunk_count: number;
};

type UploadResult = {
  document: DocumentItem;
  auto_indexed: boolean;
  chunk_count: number;
  embedding_provider: string;
  embedding_dimensions: number;
};

type DeleteResult = {
  document_id: string;
  title: string;
  deleted_chunk_count: number;
  removed_from_index: boolean;
  raw_file_deleted: boolean;
  processed_artifact_deleted: boolean;
};

type RetrievedChunk = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  source_filename: string;
  section_path: string | null;
  page_start: number;
  page_end: number;
  score: number;
  text: string;
  chunk_metadata: Record<string, unknown>;
};

type AnswerCitation = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  source_filename: string;
  section_path: string | null;
  page_start: number;
  page_end: number;
  score: number;
  quote_preview: string;
  support: string | null;
};

type AnswerResult = {
  question: string;
  answer: string;
  abstained: boolean;
  confidence: "high" | "medium" | "low";
  confidence_reasons: string[];
  answer_model: string;
  embedding_provider: string;
  top_k: number;
  citations: AnswerCitation[];
  retrieved_chunks: RetrievedChunk[];
};

type CorpusEvent = {
  title: string;
  action_label: string;
  chunk_count: number;
  embedding_provider?: string | null;
};

type DocumentSort = "updated_desc" | "title_asc" | "chunks_desc" | "effective_desc";
type DensityMode = "comfortable" | "compact";


const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const documentSortOptions: DocumentSort[] = ["updated_desc", "title_asc", "chunks_desc", "effective_desc"];
const pageSizeOptions = [6, 10, 16];


export function PhaseOneConsole() {
  const [file, setFile] = useState<File | null>(null);
  const [uploadInputKey, setUploadInputKey] = useState(0);
  const [question, setQuestion] = useState("What is the urgent prior authorization escalation process?");
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDepartment, setSelectedDepartment] = useState("all");
  const [selectedDocumentType, setSelectedDocumentType] = useState("all");
  const [selectedPolicyStatus, setSelectedPolicyStatus] = useState("all");
  const [documentSearch, setDocumentSearch] = useState("");
  const [documentStatusFilter, setDocumentStatusFilter] = useState("all");
  const [libraryDocumentTypeFilter, setLibraryDocumentTypeFilter] = useState("all");
  const [libraryDepartmentFilter, setLibraryDepartmentFilter] = useState("all");
  const [documentSort, setDocumentSort] = useState<DocumentSort>("updated_desc");
  const [density, setDensity] = useState<DensityMode>("comfortable");
  const [pageSize, setPageSize] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);
  const [latestCorpusEvent, setLatestCorpusEvent] = useState<CorpusEvent | null>(null);
  const [answerResult, setAnswerResult] = useState<AnswerResult | null>(null);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [libraryMessage, setLibraryMessage] = useState<string | null>(null);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [answerMessage, setAnswerMessage] = useState<string | null>(null);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isAnswering, setIsAnswering] = useState(false);
  const [reindexingId, setReindexingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    void loadDocuments();
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [documentSearch, documentStatusFilter, libraryDocumentTypeFilter, libraryDepartmentFilter, documentSort, pageSize]);

  useEffect(() => {
    if (selectedDocumentId && !documents.some((document) => document.id === selectedDocumentId)) {
      setSelectedDocumentId(null);
    }
    if (deleteTargetId && !documents.some((document) => document.id === deleteTargetId)) {
      setDeleteTargetId(null);
    }
  }, [deleteTargetId, documents, selectedDocumentId]);

  async function loadDocuments() {
    setIsLoadingDocuments(true);
    try {
      const response = await fetch(`${apiBaseUrl}/api/documents`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Failed to load documents");
      }
      setDocuments(payload);
      setLibraryError(null);
    } catch (caughtError) {
      setLibraryError(caughtError instanceof Error ? caughtError.message : "Failed to load documents");
    } finally {
      setIsLoadingDocuments(false);
    }
  }

  function noteCorpusChanged() {
    const hadAnswer = Boolean(answerResult);
    setAnswerResult(null);
    setSelectedEvidenceId(null);
    setAnswerError(null);
    setAnswerMessage(hadAnswer ? "Corpus changed. Generate a fresh answer against the updated source set." : null);
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setLibraryError("Choose a PDF before uploading.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);
    setLibraryError(null);
    setLibraryMessage(null);
    setIsUploading(true);

    try {
      const response = await fetch(`${apiBaseUrl}/api/documents/upload`, {
        method: "POST",
        body: formData,
      });
      const payload: UploadResult | { detail?: string } = await response.json();
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Upload failed" : "Upload failed");
      }

      const result = payload as UploadResult;
      setLatestCorpusEvent({
        title: result.document.title,
        action_label: "Uploaded and indexed",
        chunk_count: result.chunk_count,
        embedding_provider: result.embedding_provider,
      });
      setLibraryMessage(
        `Indexed ${result.chunk_count} chunk${result.chunk_count === 1 ? "" : "s"} from ${result.document.title}.`
      );
      setFile(null);
      setUploadInputKey((current) => current + 1);
      noteCorpusChanged();
      await loadDocuments();
    } catch (caughtError) {
      setLibraryError(caughtError instanceof Error ? caughtError.message : "Upload failed");
      await loadDocuments();
    } finally {
      setIsUploading(false);
    }
  }

  async function handleReindex(document: DocumentItem) {
    setLibraryError(null);
    setLibraryMessage(null);
    setReindexingId(document.id);

    try {
      const response = await fetch(`${apiBaseUrl}/api/documents/${document.id}/index`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Reindex failed");
      }

      setLatestCorpusEvent({
        title: payload.document.title,
        action_label: "Reindexed",
        chunk_count: payload.chunk_count,
        embedding_provider: payload.embedding_provider,
      });
      setLibraryMessage(
        `Reindexed ${payload.chunk_count} chunk${payload.chunk_count === 1 ? "" : "s"} for ${payload.document.title}.`
      );
      noteCorpusChanged();
      await loadDocuments();
    } catch (caughtError) {
      setLibraryError(caughtError instanceof Error ? caughtError.message : "Reindex failed");
    } finally {
      setReindexingId(null);
    }
  }

  async function handleDeleteConfirm() {
    if (!deleteTargetId) {
      return;
    }

    const target = documents.find((document) => document.id === deleteTargetId);
    if (!target) {
      setDeleteTargetId(null);
      return;
    }

    setLibraryError(null);
    setLibraryMessage(null);
    setDeletingId(target.id);

    try {
      const response = await fetch(`${apiBaseUrl}/api/documents/${target.id}`, {
        method: "DELETE",
      });
      const payload: DeleteResult | { detail?: string } = await response.json();
      if (!response.ok) {
        throw new Error("detail" in payload ? payload.detail ?? "Delete failed" : "Delete failed");
      }

      const result = payload as DeleteResult;
      setDocuments((current) => current.filter((document) => document.id !== result.document_id));
      setDeleteTargetId(null);
      if (selectedDocumentId === result.document_id) {
        setSelectedDocumentId(null);
      }
      setLatestCorpusEvent({
        title: result.title,
        action_label: "Deleted from corpus",
        chunk_count: result.deleted_chunk_count,
      });
      setLibraryMessage(
        [
          `Deleted ${result.title}.`,
          result.removed_from_index
            ? `Removed ${result.deleted_chunk_count} searchable chunk${result.deleted_chunk_count === 1 ? "" : "s"}.`
            : "Removed its document record.",
          result.raw_file_deleted ? "Raw file removed." : "Raw file was already missing.",
          result.processed_artifact_deleted ? "Processed artifact removed." : "No processed artifact found.",
        ].join(" ")
      );
      noteCorpusChanged();
    } catch (caughtError) {
      setLibraryError(caughtError instanceof Error ? caughtError.message : "Delete failed");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleAnswer() {
    setAnswerError(null);
    setAnswerMessage(null);
    setIsAnswering(true);

    const filters: Record<string, string> = {};
    if (selectedDepartment !== "all") {
      filters.department = selectedDepartment;
    }
    if (selectedDocumentType !== "all") {
      filters.document_type = selectedDocumentType;
    }
    if (selectedPolicyStatus !== "all") {
      filters.policy_status = selectedPolicyStatus;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          top_k: 5,
          filters: Object.keys(filters).length ? filters : undefined,
        }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Answer generation failed");
      }

      setAnswerResult(payload);
      setSelectedEvidenceId(payload.citations[0]?.chunk_id ?? payload.retrieved_chunks[0]?.chunk_id ?? null);
      setAnswerMessage(
        payload.abstained
          ? "The model abstained because the evidence was weak or incomplete."
          : `Generated a grounded answer from ${payload.citations.length} cited chunk${payload.citations.length === 1 ? "" : "s"}.`
      );
    } catch (caughtError) {
      setAnswerError(caughtError instanceof Error ? caughtError.message : "Answer generation failed");
    } finally {
      setIsAnswering(false);
    }
  }

  const indexedDocuments = documents.filter((document) => document.ingestion_status === "indexed");
  const attentionDocuments = documents.filter((document) => document.ingestion_status !== "indexed");
  const activePolicies = documents.filter((document) => document.policy_status === "active");
  const totalChunks = documents.reduce((sum, document) => sum + document.chunk_count, 0);

  const departmentOptions = uniqueStrings(documents.map((document) => document.department));
  const documentTypeOptions = uniqueStrings(documents.map((document) => document.document_type));
  const policyStatusOptions = uniqueStrings(documents.map((document) => document.policy_status));
  const ingestionStatusOptions = uniqueStrings(documents.map((document) => document.ingestion_status));

  const filteredDocuments = useMemo(() => {
    const query = documentSearch.trim().toLowerCase();
    const filtered = documents.filter((document) => {
      if (documentStatusFilter !== "all" && document.ingestion_status !== documentStatusFilter) {
        return false;
      }
      if (libraryDocumentTypeFilter !== "all" && document.document_type !== libraryDocumentTypeFilter) {
        return false;
      }
      if (libraryDepartmentFilter !== "all" && document.department !== libraryDepartmentFilter) {
        return false;
      }
      if (!query) {
        return true;
      }

      const haystack = [
        document.title,
        document.source_filename,
        document.ingestion_status,
        document.document_type ?? "",
        document.department ?? "",
        document.policy_status ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });

    return filtered.sort((left, right) => compareDocuments(left, right, documentSort));
  }, [documentSearch, documentSort, documentStatusFilter, documents, libraryDepartmentFilter, libraryDocumentTypeFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredDocuments.length / pageSize));
  const pageStartIndex = (currentPage - 1) * pageSize;
  const paginatedDocuments = filteredDocuments.slice(pageStartIndex, pageStartIndex + pageSize);
  const paginationItems = buildPagination(currentPage, totalPages);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId]
  );
  const deleteTarget = useMemo(
    () => documents.find((document) => document.id === deleteTargetId) ?? null,
    [deleteTargetId, documents]
  );

  const evidenceById = useMemo(() => {
    const map = new Map<string, RetrievedChunk>();
    for (const chunk of answerResult?.retrieved_chunks ?? []) {
      map.set(chunk.chunk_id, chunk);
    }
    return map;
  }, [answerResult]);

  const citationById = useMemo(() => {
    const map = new Map<string, AnswerCitation>();
    for (const citation of answerResult?.citations ?? []) {
      map.set(citation.chunk_id, citation);
    }
    return map;
  }, [answerResult]);

  const selectedEvidence = selectedEvidenceId ? evidenceById.get(selectedEvidenceId) ?? null : null;
  const selectedCitation = selectedEvidenceId ? citationById.get(selectedEvidenceId) ?? null : null;

  const activeAnswerFilters = [
    selectedDepartment !== "all" ? `Department: ${readableLabel(selectedDepartment)}` : null,
    selectedDocumentType !== "all" ? `Type: ${readableLabel(selectedDocumentType)}` : null,
    selectedPolicyStatus !== "all" ? `Policy status: ${readableLabel(selectedPolicyStatus)}` : null,
  ].filter((value): value is string => Boolean(value));

  const hasLibraryFilters =
    documentSearch.trim().length > 0 ||
    documentStatusFilter !== "all" ||
    libraryDocumentTypeFilter !== "all" ||
    libraryDepartmentFilter !== "all";

  return (
    <>
      <section className="rounded-[34px] border border-white/70 bg-paper/92 p-6 shadow-card backdrop-blur md:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.26em] text-clay">Answer Workspace</p>
            <h2 className="font-[var(--font-display)] text-4xl font-bold text-slate md:text-[2.8rem]">
              Ask Grounded Questions Against The Corpus
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate/74">
              This is the primary workflow. Use the indexed document set to generate evidence-backed answers, then inspect
              the source excerpts before trusting the response.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <TopMetric label="Searchable Docs" value={String(indexedDocuments.length)} />
            <TopMetric label="Active Policies" value={String(activePolicies.length)} />
            <TopMetric label="Total Chunks" value={String(totalChunks)} />
          </div>
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-6">
            <section className="rounded-[30px] border border-slate/10 bg-white p-5 md:p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-moss">Question Composer</p>
                  <p className="mt-2 text-sm leading-6 text-slate/68">
                    Ask about policy coverage, escalation paths, review timing, documentation rules, or operational
                    procedures.
                  </p>
                </div>
                <div className="rounded-full border border-slate/10 bg-sand px-4 py-2 text-sm text-slate">
                  Searching {indexedDocuments.length} doc{indexedDocuments.length === 1 ? "" : "s"}
                </div>
              </div>

              <div className="mt-5 rounded-[26px] border border-slate/10 bg-sand/45 p-4">
                <label className="mb-3 block text-xs font-semibold uppercase tracking-[0.16em] text-moss">
                  Grounded Question
                </label>
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Example: What is the urgent prior authorization escalation process?"
                  className="min-h-44 w-full rounded-[22px] border border-slate/10 bg-white px-4 py-4 text-sm leading-7 text-slate"
                />
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-3">
                <FilterSelect
                  label="Department"
                  value={selectedDepartment}
                  options={departmentOptions}
                  onChange={setSelectedDepartment}
                />
                <FilterSelect
                  label="Document Type"
                  value={selectedDocumentType}
                  options={documentTypeOptions}
                  onChange={setSelectedDocumentType}
                />
                <FilterSelect
                  label="Policy Status"
                  value={selectedPolicyStatus}
                  options={policyStatusOptions}
                  onChange={setSelectedPolicyStatus}
                />
              </div>

              <div className="mt-5 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex flex-wrap gap-2">
                  {activeAnswerFilters.length ? (
                    activeAnswerFilters.map((filter) => <Badge key={filter}>{filter}</Badge>)
                  ) : (
                    <span className="text-sm text-slate/62">No answer filters applied.</span>
                  )}
                </div>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedDepartment("all");
                      setSelectedDocumentType("all");
                      setSelectedPolicyStatus("all");
                    }}
                    className="rounded-2xl border border-slate/10 bg-white px-4 py-3 text-sm font-semibold text-slate transition hover:bg-sand"
                  >
                    Clear Filters
                  </button>
                  <button
                    type="button"
                    onClick={handleAnswer}
                    disabled={isAnswering || !indexedDocuments.length}
                    className="rounded-2xl bg-moss px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#58623f] disabled:opacity-60"
                  >
                    {isAnswering ? "Generating..." : "Generate Grounded Answer"}
                  </button>
                </div>
              </div>
            </section>

            {answerMessage ? (
              <Banner tone={answerResult?.abstained ? "warning" : "success"}>{answerMessage}</Banner>
            ) : null}

            {answerError ? <Banner tone="danger">{answerError}</Banner> : null}

            <section className="rounded-[30px] border border-slate/10 bg-white p-5 md:p-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-moss">Grounded Answer</p>
                  <p className="mt-2 text-sm text-slate/68">
                    {answerResult
                      ? answerResult.abstained
                        ? "The model declined to answer confidently from the current evidence."
                        : "Answer generated from retrieved policy evidence."
                      : "Generate a grounded answer to inspect reasoning, confidence, and citations."}
                  </p>
                </div>
                {answerResult ? (
                  <div className="flex flex-wrap justify-end gap-2">
                    <Badge tone={confidenceTone(answerResult.confidence)}>{answerResult.confidence} confidence</Badge>
                    <Badge>{answerResult.answer_model}</Badge>
                    <Badge>{answerResult.embedding_provider}</Badge>
                  </div>
                ) : null}
              </div>

              {answerResult ? (
                <>
                  <div className="mt-5 rounded-[26px] border border-slate/10 bg-sand/40 p-6">
                    <p className="text-[1.02rem] leading-8 text-slate/88">{answerResult.answer}</p>
                  </div>

                  <div className="mt-5 grid gap-5 xl:grid-cols-[0.82fr_1.18fr]">
                    <div className="rounded-[24px] border border-slate/10 bg-sand/25 p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Confidence Rationale</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {answerResult.confidence_reasons.map((reason) => (
                          <span
                            key={reason}
                            className="rounded-full border border-slate/10 bg-white px-3 py-2 text-sm text-slate/78"
                          >
                            {reason}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="rounded-[24px] border border-slate/10 bg-sand/25 p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Citations</p>
                      <div className="mt-3 flex flex-wrap gap-3">
                        {answerResult.citations.length ? (
                          answerResult.citations.map((citation, index) => (
                            <button
                              key={citation.chunk_id}
                              type="button"
                              onClick={() => setSelectedEvidenceId(citation.chunk_id)}
                              className={`rounded-2xl border px-4 py-3 text-left transition ${
                                selectedEvidenceId === citation.chunk_id
                                  ? "border-moss bg-[#eef3e6]"
                                  : "border-slate/10 bg-white hover:bg-sand"
                              }`}
                            >
                              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-clay">
                                Citation {index + 1}
                              </p>
                              <p className="mt-1 text-sm font-semibold text-slate">{citation.document_title}</p>
                              <p className="mt-1 text-sm text-slate/68">
                                {citation.section_path ?? "General section"} | pages {citation.page_start}-{citation.page_end}
                              </p>
                            </button>
                          ))
                        ) : (
                          <div className="rounded-2xl border border-dashed border-slate/15 bg-white px-4 py-4 text-sm text-slate/65">
                            No citations were returned for this answer.
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="mt-5 rounded-[26px] border border-dashed border-slate/15 bg-sand/30 px-5 py-12 text-sm leading-7 text-slate/65">
                  Upload and index source documents, then ask a grounded question. The answer will appear here with
                  confidence and citations.
                </div>
              )}
            </section>
          </div>

          <div className="space-y-6">
            <section className="rounded-[30px] border border-slate/10 bg-white p-5 md:p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-moss">Grounding Scope</p>
                  <p className="mt-2 text-sm leading-6 text-slate/68">
                    The answer workflow only has access to indexed documents and the filters you apply here.
                  </p>
                </div>
                <Badge tone={attentionDocuments.length ? "warning" : "success"}>
                  {attentionDocuments.length ? "review needed" : "ready"}
                </Badge>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <MetricCard label="Indexed Docs" value={String(indexedDocuments.length)} note="available to search" />
                <MetricCard label="Corpus Chunks" value={String(totalChunks)} note="retrieval units" />
                <MetricCard label="Attention Items" value={String(attentionDocuments.length)} note="pending or failed" />
                <MetricCard label="Active Policies" value={String(activePolicies.length)} note="currently marked active" />
              </div>

              <div className="mt-5 rounded-[24px] border border-slate/10 bg-sand/25 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Current Filters</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {activeAnswerFilters.length ? (
                    activeAnswerFilters.map((filter) => <Badge key={filter}>{filter}</Badge>)
                  ) : (
                    <span className="text-sm text-slate/62">All indexed documents are in scope.</span>
                  )}
                </div>
              </div>
            </section>

            <section className="rounded-[30px] border border-slate/10 bg-white p-5 md:p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold uppercase tracking-[0.18em] text-moss">Evidence Explorer</p>
                  <p className="mt-2 text-sm text-slate/68">
                    Review the top retrieved chunks and the selected source excerpt in one place.
                  </p>
                </div>
                {answerResult ? <Badge>{answerResult.top_k} top-k</Badge> : null}
              </div>

              {answerResult?.retrieved_chunks.length ? (
                <>
                  <div className="mt-5 max-h-[20rem] space-y-3 overflow-y-auto pr-1">
                    {answerResult.retrieved_chunks.map((chunk, index) => (
                      <button
                        key={chunk.chunk_id}
                        type="button"
                        onClick={() => setSelectedEvidenceId(chunk.chunk_id)}
                        className={`block w-full rounded-[22px] border p-4 text-left transition ${
                          selectedEvidenceId === chunk.chunk_id
                            ? "border-moss bg-[#eef3e6]"
                            : "border-slate/10 bg-sand/30 hover:bg-sand/55"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-clay">Result {index + 1}</p>
                            <h3 className="mt-1 font-[var(--font-display)] text-lg font-semibold text-slate">
                              {chunk.document_title}
                            </h3>
                            <p className="mt-1 text-sm text-slate/68">
                              {chunk.section_path ?? "General section"} | pages {chunk.page_start}-{chunk.page_end}
                            </p>
                          </div>
                          <Badge>{chunk.score.toFixed(3)}</Badge>
                        </div>
                        <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate/78">{chunk.text}</p>
                      </button>
                    ))}
                  </div>

                  <div className="mt-5 rounded-[24px] border border-slate/10 bg-sand/20 p-4">
                    {selectedEvidence ? (
                      <div className="space-y-4">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Selected Evidence</p>
                            <h3 className="mt-2 font-[var(--font-display)] text-xl font-semibold text-slate">
                              {selectedEvidence.document_title}
                            </h3>
                            <p className="mt-1 text-sm text-slate/68">
                              {selectedEvidence.section_path ?? "General section"} | pages {selectedEvidence.page_start}-
                              {selectedEvidence.page_end}
                            </p>
                          </div>
                          <Badge>{selectedEvidence.score.toFixed(3)}</Badge>
                        </div>

                        {selectedCitation?.support ? (
                          <div className="rounded-2xl border border-[#d8ccb5] bg-[#fff8ee] px-4 py-3 text-sm text-slate/78">
                            {selectedCitation.support}
                          </div>
                        ) : null}

                        <div className="rounded-2xl border border-slate/10 bg-white p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Quoted Preview</p>
                          <p className="mt-3 text-sm leading-7 text-slate/84">
                            {selectedCitation?.quote_preview ?? truncateText(selectedEvidence.text, 320)}
                          </p>
                        </div>

                        <div className="max-h-[18rem] overflow-y-auto rounded-2xl border border-slate/10 bg-white p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Full Chunk Text</p>
                          <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate/84">{selectedEvidence.text}</p>
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-2xl border border-dashed border-slate/15 bg-white px-4 py-10 text-sm leading-6 text-slate/65">
                        Select a retrieved chunk or citation to inspect the source text.
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="mt-5 rounded-[24px] border border-dashed border-slate/15 bg-sand/30 px-4 py-12 text-sm leading-6 text-slate/65">
                  Retrieved evidence will appear here after you generate a grounded answer.
                </div>
              )}
            </section>
          </div>
        </div>
      </section>

      <section className="mt-6 rounded-[34px] border border-white/70 bg-paper/92 p-6 shadow-card backdrop-blur md:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.26em] text-clay">Corpus Operations</p>
            <h2 className="font-[var(--font-display)] text-3xl font-bold text-slate md:text-[2.45rem]">
              Ingest, Monitor, And Manage Source Documents
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate/74">
              Corpus management is secondary to asking questions, but it needs to stay operationally clear: documents
              must be searchable, current, and easy to inspect at scale.
            </p>
          </div>
          <div className="rounded-full border border-slate/10 bg-sand px-4 py-2 text-sm text-slate">
            API: {apiBaseUrl}
          </div>
        </div>

        <div className="mt-6 grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
          <form onSubmit={handleUpload} className="rounded-[30px] border border-slate/10 bg-white p-5 md:p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-moss">Ingestion Flow</p>
                <p className="mt-2 text-sm leading-6 text-slate/68">
                  Add a new source document to the corpus. Uploading triggers storage, parsing, chunking, embedding, and
                  index registration automatically.
                </p>
              </div>
              <Badge tone="neutral">PDF only</Badge>
            </div>

            <div className="mt-5 grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
              <label className="block cursor-pointer rounded-[26px] border border-dashed border-slate/20 bg-sand/45 p-5 transition hover:border-moss/35 hover:bg-sand/65">
                <input
                  key={uploadInputKey}
                  type="file"
                  accept="application/pdf"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  className="hidden"
                />
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-lg font-semibold text-slate">{file ? "Replace Selected File" : "Choose Source PDF"}</p>
                    <p className="mt-2 text-sm leading-6 text-slate/68">
                      Best results come from text-based healthcare policy, manual, and procedure PDFs with clear section
                      structure.
                    </p>
                  </div>
                  <span className="rounded-full border border-slate/10 bg-white px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-moss">
                    browse
                  </span>
                </div>

                <div className="mt-5 flex flex-wrap gap-2">
                  <Badge>auto parse</Badge>
                  <Badge>auto index</Badge>
                  <Badge>retrieval ready</Badge>
                </div>

                <div className="mt-6 rounded-[22px] border border-slate/10 bg-white px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Selected File</p>
                  <p className="mt-2 text-sm text-slate/78">
                    {file ? file.name : "No file selected yet. Click here to choose a PDF for ingestion."}
                  </p>
                </div>
              </label>

              <div className="rounded-[26px] border border-slate/10 bg-[#fbf7ef] p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">What Happens Next</p>
                <div className="mt-4 space-y-3">
                  <StepRow number="1" title="Store Source" detail="The raw PDF is registered in the corpus." />
                  <StepRow number="2" title="Index Content" detail="Pages are chunked, embedded, and pushed into search." />
                  <StepRow number="3" title="Go Live" detail="The document becomes available for grounded answers." />
                </div>
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <p className="text-sm leading-6 text-slate/66">
                Use upload when adding a new source. Use reindex from the registry when reprocessing an existing document.
              </p>
              <button
                type="submit"
                disabled={isUploading}
                className="rounded-2xl bg-slate px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#101820] disabled:opacity-60"
              >
                {isUploading ? "Uploading & Indexing..." : "Upload & Index"}
              </button>
            </div>
          </form>

          <div className="rounded-[30px] border border-slate/10 bg-white p-5 md:p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-moss">Corpus Health</p>
                <p className="mt-2 text-sm leading-6 text-slate/68">
                  Track overall readiness and quickly spot records that need operational attention.
                </p>
              </div>
              <Badge tone={attentionDocuments.length ? "warning" : "success"}>
                {attentionDocuments.length ? "attention" : "healthy"}
              </Badge>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <MetricCard label="Corpus Docs" value={String(documents.length)} note="registered sources" />
              <MetricCard label="Indexed" value={String(indexedDocuments.length)} note="searchable now" />
              <MetricCard label="Attention" value={String(attentionDocuments.length)} note="pending or failed" />
              <MetricCard label="Chunks" value={String(totalChunks)} note="retrieval units" />
            </div>

            <div className="mt-5 rounded-[24px] border border-slate/10 bg-sand/25 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Operational Snapshot</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge>{activePolicies.length} active {activePolicies.length === 1 ? "policy" : "policies"}</Badge>
                <Badge>{documents.length - activePolicies.length} non-active or unspecified</Badge>
                <Badge>{documents.length ? Math.round((indexedDocuments.length / documents.length) * 100) : 0}% indexed</Badge>
              </div>
            </div>
          </div>
        </div>

        {latestCorpusEvent ? (
          <div className="mt-5 rounded-[24px] border border-[#d8ccb5] bg-[#fff8ee] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold uppercase tracking-[0.18em] text-clay">Latest Corpus Event</p>
                <p className="mt-2 text-sm leading-6 text-slate/78">
                  {latestCorpusEvent.action_label} for {latestCorpusEvent.title}.
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate">
                <Badge>{latestCorpusEvent.chunk_count} chunk{latestCorpusEvent.chunk_count === 1 ? "" : "s"}</Badge>
                {latestCorpusEvent.embedding_provider ? <Badge>{latestCorpusEvent.embedding_provider}</Badge> : null}
              </div>
            </div>
          </div>
        ) : null}

        {libraryMessage ? <Banner tone="success" className="mt-5">{libraryMessage}</Banner> : null}
        {libraryError ? <Banner tone="danger" className="mt-5">{libraryError}</Banner> : null}

        <section className="mt-6 rounded-[30px] border border-slate/10 bg-white p-5 md:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.18em] text-moss">Corpus Registry</p>
              <p className="mt-2 text-sm leading-6 text-slate/68">
                Browse the corpus with pagination, inspect metadata in a detail drawer, and take deliberate reindex or
                delete actions.
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadDocuments()}
              disabled={isLoadingDocuments}
              className="rounded-2xl border border-slate/10 bg-white px-4 py-2 text-sm font-semibold text-slate transition hover:bg-sand disabled:opacity-60"
            >
              {isLoadingDocuments ? "Refreshing..." : "Refresh"}
            </button>
          </div>

          <div className="mt-5 grid gap-3 xl:grid-cols-[1.3fr_repeat(3,minmax(0,0.82fr))]">
            <SearchField label="Search Library" value={documentSearch} onChange={setDocumentSearch} />
            <FilterSelect
              label="Status"
              value={documentStatusFilter}
              options={ingestionStatusOptions}
              onChange={setDocumentStatusFilter}
            />
            <FilterSelect
              label="Document Type"
              value={libraryDocumentTypeFilter}
              options={documentTypeOptions}
              onChange={setLibraryDocumentTypeFilter}
            />
            <FilterSelect
              label="Department"
              value={libraryDepartmentFilter}
              options={departmentOptions}
              onChange={setLibraryDepartmentFilter}
            />
          </div>

          <div className="mt-4 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <p className="text-sm leading-6 text-slate/68">
              Showing {paginatedDocuments.length ? pageStartIndex + 1 : 0}-
              {Math.min(pageStartIndex + paginatedDocuments.length, filteredDocuments.length)} of {filteredDocuments.length}
              {" "}document{filteredDocuments.length === 1 ? "" : "s"}.
            </p>

            <div className="flex flex-wrap gap-3">
              <FilterSelect
                label="Sort"
                value={documentSort}
                options={documentSortOptions}
                onChange={(value) => setDocumentSort(value as DocumentSort)}
                showAllOption={false}
                formatOptionLabel={formatSortLabel}
                containerClassName="min-w-[11rem]"
              />
              <FilterSelect
                label="Rows"
                value={String(pageSize)}
                options={pageSizeOptions.map(String)}
                onChange={(value) => setPageSize(Number(value))}
                showAllOption={false}
                containerClassName="min-w-[7rem]"
              />
              <DensityToggle value={density} onChange={setDensity} />
              {hasLibraryFilters ? (
                <button
                  type="button"
                  onClick={() => {
                    setDocumentSearch("");
                    setDocumentStatusFilter("all");
                    setLibraryDocumentTypeFilter("all");
                    setLibraryDepartmentFilter("all");
                  }}
                  className="rounded-2xl border border-slate/10 bg-white px-4 py-3 text-sm font-semibold text-slate transition hover:bg-sand"
                >
                  Clear Filters
                </button>
              ) : null}
            </div>
          </div>

          <div className="mt-5 overflow-hidden rounded-[24px] border border-slate/10">
            {isLoadingDocuments && !documents.length ? (
              <div className="space-y-3 bg-white px-4 py-4">
                {Array.from({ length: 6 }).map((_, index) => (
                  <div key={index} className="h-16 animate-pulse rounded-2xl bg-sand/55" />
                ))}
              </div>
            ) : filteredDocuments.length ? (
              <div className="overflow-auto">
                <table className="w-full min-w-[980px] border-collapse">
                  <thead className="bg-sand/65 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-slate/65">
                    <tr>
                      <th className="px-4 py-3">Document</th>
                      <th className="px-4 py-3">Corpus Status</th>
                      <th className="px-4 py-3">Classification</th>
                      <th className="px-4 py-3">Coverage</th>
                      <th className="px-4 py-3">Freshness</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="bg-white">
                    {paginatedDocuments.map((document) => (
                      <DocumentRow
                        key={document.id}
                        document={document}
                        density={density}
                        isDeleting={deletingId === document.id}
                        isReindexing={reindexingId === document.id}
                        isSelected={selectedDocumentId === document.id}
                        onDelete={() => setDeleteTargetId(document.id)}
                        onOpen={() => setSelectedDocumentId(document.id)}
                        onReindex={() => void handleReindex(document)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : documents.length ? (
              <div className="bg-white px-5 py-10 text-sm leading-6 text-slate/65">
                No documents match the current search and filters.
              </div>
            ) : (
              <div className="bg-white px-5 py-10 text-sm leading-6 text-slate/65">
                No documents in the corpus yet. Upload the first policy PDF to create a searchable source set.
              </div>
            )}
          </div>

          {filteredDocuments.length ? (
            <div className="mt-5 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <p className="text-sm text-slate/66">
                Page {currentPage} of {totalPages}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                  disabled={currentPage === 1}
                  className="rounded-2xl border border-slate/10 bg-white px-4 py-2 text-sm font-semibold text-slate transition hover:bg-sand disabled:opacity-50"
                >
                  Previous
                </button>
                {paginationItems.map((item, index) =>
                  item === "ellipsis" ? (
                    <span key={`${item}-${index}`} className="px-2 text-sm text-slate/55">
                      …
                    </span>
                  ) : (
                    <button
                      key={item}
                      type="button"
                      onClick={() => setCurrentPage(item)}
                      className={`rounded-2xl px-4 py-2 text-sm font-semibold transition ${
                        item === currentPage
                          ? "bg-slate text-white"
                          : "border border-slate/10 bg-white text-slate hover:bg-sand"
                      }`}
                    >
                      {item}
                    </button>
                  )
                )}
                <button
                  type="button"
                  onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                  disabled={currentPage === totalPages}
                  className="rounded-2xl border border-slate/10 bg-white px-4 py-2 text-sm font-semibold text-slate transition hover:bg-sand disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          ) : null}
        </section>
      </section>

      {selectedDocument ? (
        <DocumentDetailDrawer
          deletingId={deletingId}
          document={selectedDocument}
          reindexingId={reindexingId}
          onClose={() => setSelectedDocumentId(null)}
          onDelete={() => setDeleteTargetId(selectedDocument.id)}
          onReindex={() => void handleReindex(selectedDocument)}
        />
      ) : null}

      {deleteTarget ? (
        <DeleteConfirmationDialog
          document={deleteTarget}
          isDeleting={deletingId === deleteTarget.id}
          onCancel={() => setDeleteTargetId(null)}
          onConfirm={() => void handleDeleteConfirm()}
        />
      ) : null}
    </>
  );
}


function DocumentRow({
  document,
  density,
  isDeleting,
  isReindexing,
  isSelected,
  onDelete,
  onOpen,
  onReindex,
}: {
  document: DocumentItem;
  density: DensityMode;
  isDeleting: boolean;
  isReindexing: boolean;
  isSelected: boolean;
  onDelete: () => void;
  onOpen: () => void;
  onReindex: () => void;
}) {
  const rowPadding = density === "compact" ? "py-3" : "py-4";

  return (
    <tr className={`border-t border-slate/10 align-top transition ${isSelected ? "bg-[#f8fbf4]" : "hover:bg-sand/25"}`}>
      <td className={`px-4 ${rowPadding}`}>
        <button type="button" onClick={onOpen} className="text-left">
          <p className="font-semibold text-slate transition hover:text-moss">{document.title}</p>
          <p className="mt-1 text-sm text-slate/62">{document.source_filename}</p>
          <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate/48">
            ID {document.id.slice(0, 8)}
          </p>
        </button>
      </td>
      <td className={`px-4 ${rowPadding}`}>
        <div className="space-y-2">
          <Badge tone={statusTone(document.ingestion_status)}>{document.ingestion_status}</Badge>
          <p className="text-sm text-slate/66">
            {document.ingestion_status === "indexed"
              ? "Searchable now"
              : document.ingestion_status === "failed"
                ? "Needs review"
                : "Stored but not searchable"}
          </p>
          {document.policy_status ? (
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate/54">
              {readableLabel(document.policy_status)}
            </span>
          ) : null}
        </div>
      </td>
      <td className={`px-4 ${rowPadding}`}>
        <div className="space-y-2 text-sm text-slate/72">
          <div className="flex flex-wrap gap-2">
            {document.document_type ? <Badge>{readableLabel(document.document_type)}</Badge> : null}
            {document.department ? <Badge>{readableLabel(document.department)}</Badge> : null}
          </div>
          <p>{document.document_type || document.department ? "Classified" : "Awaiting metadata enrichment"}</p>
        </div>
      </td>
      <td className={`px-4 ${rowPadding}`}>
        <div className="space-y-2 text-sm text-slate/72">
          <p>
            {document.page_count} page{document.page_count === 1 ? "" : "s"}
          </p>
          <p>
            {document.chunk_count} chunk{document.chunk_count === 1 ? "" : "s"}
          </p>
        </div>
      </td>
      <td className={`px-4 ${rowPadding}`}>
        <div className="space-y-2 text-sm text-slate/72">
          <p>{formatDate(document.updated_at)}</p>
          <p>Effective {formatDate(document.effective_date)}</p>
        </div>
      </td>
      <td className={`px-4 ${rowPadding} text-right`}>
        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onOpen}
            className="rounded-2xl border border-slate/10 bg-white px-3 py-2 text-sm font-semibold text-slate transition hover:bg-sand"
          >
            Open
          </button>
          <button
            type="button"
            onClick={onReindex}
            disabled={isReindexing || isDeleting}
            className="rounded-2xl bg-clay px-3 py-2 text-sm font-semibold text-white transition hover:bg-[#a45736] disabled:opacity-60"
          >
            {isReindexing ? "Working..." : document.ingestion_status === "indexed" ? "Reindex" : "Index"}
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={isDeleting || isReindexing}
            className="rounded-2xl border border-[#d9a37f] bg-[#fff1e8] px-3 py-2 text-sm font-semibold text-[#9a4129] transition hover:bg-[#ffe8db] disabled:opacity-60"
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </button>
        </div>
      </td>
    </tr>
  );
}


function DocumentDetailDrawer({
  document,
  reindexingId,
  deletingId,
  onClose,
  onReindex,
  onDelete,
}: {
  document: DocumentItem;
  reindexingId: string | null;
  deletingId: string | null;
  onClose: () => void;
  onReindex: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="fixed inset-0 z-40">
      <button
        type="button"
        aria-label="Close document drawer"
        onClick={onClose}
        className="absolute inset-0 bg-slate/30 backdrop-blur-[1px]"
      />
      <aside className="absolute right-0 top-0 h-full w-full max-w-xl overflow-y-auto border-l border-slate/10 bg-[#fbf6ee] p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-clay">Document Details</p>
            <h3 className="mt-2 font-[var(--font-display)] text-3xl font-bold text-slate">{document.title}</h3>
            <p className="mt-2 text-sm leading-6 text-slate/68">{document.source_filename}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-slate/10 bg-white px-3 py-2 text-sm font-semibold text-slate transition hover:bg-sand"
          >
            Close
          </button>
        </div>

        <div className="mt-5 flex flex-wrap gap-2">
          <Badge tone={statusTone(document.ingestion_status)}>{document.ingestion_status}</Badge>
          {document.document_type ? <Badge>{readableLabel(document.document_type)}</Badge> : null}
          {document.department ? <Badge>{readableLabel(document.department)}</Badge> : null}
          {document.policy_status ? <Badge>{readableLabel(document.policy_status)}</Badge> : null}
        </div>

        <div className="mt-6 rounded-[24px] border border-slate/10 bg-white p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Corpus State</p>
          <p className="mt-3 text-sm leading-7 text-slate/78">
            {document.ingestion_status === "indexed"
              ? "This document is currently part of the searchable corpus and can ground retrieval and generated answers."
              : document.ingestion_status === "failed"
                ? "This document exists in the library but is not searchable because indexing failed. Review the ingest error before relying on it."
                : "This document has been stored but is not yet fully searchable. Run indexing to add it to the corpus."}
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <InfoLine label="Pages" value={`${document.page_count}`} />
            <InfoLine label="Chunks" value={`${document.chunk_count}`} />
            <InfoLine label="Updated" value={formatDate(document.updated_at)} />
            <InfoLine label="Effective" value={formatDate(document.effective_date)} />
          </div>
        </div>

        <div className="mt-5 rounded-[24px] border border-slate/10 bg-white p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Metadata</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <InfoLine label="Department" value={document.department ? readableLabel(document.department) : "Not detected"} />
            <InfoLine
              label="Document Type"
              value={document.document_type ? readableLabel(document.document_type) : "Not detected"}
            />
            <InfoLine label="Policy Status" value={document.policy_status ? readableLabel(document.policy_status) : "Not set"} />
            <InfoLine label="Version" value={document.version_label ?? "Not detected"} />
            <InfoLine label="Review Date" value={formatDate(document.review_date)} />
            <InfoLine label="Created" value={formatDate(document.created_at)} />
          </div>
        </div>

        <div className="mt-5 rounded-[24px] border border-slate/10 bg-white p-5">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">Operational Details</p>
          <div className="mt-4 space-y-3 text-sm text-slate/78">
            <InfoRow label="Document ID" value={document.id} />
            <InfoRow label="Source File" value={document.source_filename} />
            <InfoRow label="Parse Error" value={document.parse_error ?? "None"} tone={document.parse_error ? "danger" : "neutral"} />
          </div>
        </div>

        {document.parse_error ? <Banner tone="danger" className="mt-5">{document.parse_error}</Banner> : null}

        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={onReindex}
            disabled={reindexingId === document.id || deletingId === document.id}
            className="rounded-2xl bg-clay px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#a45736] disabled:opacity-60"
          >
            {reindexingId === document.id
              ? "Working..."
              : document.ingestion_status === "indexed"
                ? "Reindex Document"
                : "Index Document"}
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={deletingId === document.id || reindexingId === document.id}
            className="rounded-2xl border border-[#d9a37f] bg-[#fff1e8] px-4 py-3 text-sm font-semibold text-[#9a4129] transition hover:bg-[#ffe8db] disabled:opacity-60"
          >
            {deletingId === document.id ? "Deleting..." : "Delete From Corpus"}
          </button>
        </div>
      </aside>
    </div>
  );
}


function DeleteConfirmationDialog({
  document,
  isDeleting,
  onCancel,
  onConfirm,
}: {
  document: DocumentItem;
  isDeleting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-5">
      <button type="button" aria-label="Close delete dialog" onClick={onCancel} className="absolute inset-0 bg-slate/40" />
      <div className="relative w-full max-w-lg rounded-[30px] border border-slate/10 bg-white p-6 shadow-2xl">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-clay">Delete Document</p>
        <h3 className="mt-3 font-[var(--font-display)] text-3xl font-bold text-slate">{document.title}</h3>
        <p className="mt-3 text-sm leading-7 text-slate/76">
          This removes the document from the RAG corpus. The stored PDF, processed artifact, document record, and any
          indexed vector entries for this document will be removed.
        </p>

        <div className="mt-5 rounded-[24px] border border-slate/10 bg-sand/35 p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <InfoLine label="Status" value={readableLabel(document.ingestion_status)} />
            <InfoLine label="Chunks" value={`${document.chunk_count}`} />
            <InfoLine label="Pages" value={`${document.page_count}`} />
            <InfoLine label="File" value={document.source_filename} />
          </div>
        </div>

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onCancel}
            disabled={isDeleting}
            className="rounded-2xl border border-slate/10 bg-white px-4 py-3 text-sm font-semibold text-slate transition hover:bg-sand disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isDeleting}
            className="rounded-2xl bg-[#b24c2f] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#9d4127] disabled:opacity-60"
          >
            {isDeleting ? "Deleting..." : "Delete Document"}
          </button>
        </div>
      </div>
    </div>
  );
}


function TopMetric({ label, value }: { label: string; value: string }) {
  return (
    <article className="min-w-[8.5rem] rounded-[22px] border border-slate/10 bg-white px-4 py-4 text-center">
      <p className="font-[var(--font-display)] text-3xl font-bold text-slate">{value}</p>
      <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate/58">{label}</p>
    </article>
  );
}


function MetricCard({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <article className="rounded-[24px] border border-slate/10 bg-sand/45 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-moss">{label}</p>
      <p className="mt-2 font-[var(--font-display)] text-3xl font-bold text-slate">{value}</p>
      <p className="mt-2 text-sm leading-6 text-slate/66">{note}</p>
    </article>
  );
}


function SearchField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.16em] text-moss">{label}</span>
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search title, file, department..."
        className="w-full rounded-2xl border border-slate/10 bg-sand/55 px-4 py-3 text-sm text-slate"
      />
    </label>
  );
}


function FilterSelect({
  label,
  value,
  options,
  onChange,
  showAllOption = true,
  formatOptionLabel = readableLabel,
  containerClassName,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  showAllOption?: boolean;
  formatOptionLabel?: (value: string) => string;
  containerClassName?: string;
}) {
  return (
    <label className={`block ${containerClassName ?? ""}`}>
      <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.16em] text-moss">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-2xl border border-slate/10 bg-sand/55 px-4 py-3 text-sm text-slate"
      >
        {showAllOption ? <option value="all">All</option> : null}
        {options.map((option) => (
          <option key={option} value={option}>
            {formatOptionLabel(option)}
          </option>
        ))}
      </select>
    </label>
  );
}


function DensityToggle({
  value,
  onChange,
}: {
  value: DensityMode;
  onChange: (value: DensityMode) => void;
}) {
  return (
    <div className="rounded-[22px] border border-slate/10 bg-white p-1">
      <div className="flex gap-1">
        {(["comfortable", "compact"] as DensityMode[]).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => onChange(option)}
            className={`rounded-[18px] px-3 py-2 text-sm font-semibold transition ${
              value === option ? "bg-slate text-white" : "text-slate hover:bg-sand"
            }`}
          >
            {option === "comfortable" ? "Comfortable" : "Compact"}
          </button>
        ))}
      </div>
    </div>
  );
}


function StepRow({ number, title, detail }: { number: string; title: string; detail: string }) {
  return (
    <div className="flex gap-4 rounded-[22px] border border-slate/10 bg-white px-4 py-4">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate text-sm font-semibold text-white">
        {number}
      </div>
      <div>
        <p className="text-sm font-semibold text-slate">{title}</p>
        <p className="mt-1 text-sm leading-6 text-slate/66">{detail}</p>
      </div>
    </div>
  );
}


function InfoLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate/10 bg-sand/40 px-3 py-3">
      <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] text-moss">{label}</span>
      <span className="mt-1 block text-sm text-slate">{value}</span>
    </div>
  );
}


function InfoRow({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "danger";
}) {
  return (
    <div className="rounded-2xl border border-slate/10 bg-sand/30 px-4 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-moss">{label}</p>
      <p className={`mt-2 break-all text-sm ${tone === "danger" ? "text-[#9a4129]" : "text-slate/78"}`}>{value}</p>
    </div>
  );
}


function Banner({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
  className?: string;
}) {
  const toneClass =
    tone === "success"
      ? "border-[#d1e4c8] bg-[#f5fbef] text-[#456534]"
      : tone === "warning"
        ? "border-[#ead6ab] bg-[#fff8e6] text-[#8c5a14]"
        : tone === "danger"
          ? "border-[#d9a37f] bg-[#fff1e8] text-[#8d4d27]"
          : "border-slate/10 bg-white text-slate/78";

  return <div className={`${className ?? ""} rounded-2xl border px-4 py-3 text-sm ${toneClass}`}>{children}</div>;
}


function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
}) {
  const toneClass =
    tone === "success"
      ? "bg-[#edf6ea] text-[#3f6a30]"
      : tone === "warning"
        ? "bg-[#fff3dd] text-[#8c5a14]"
        : tone === "danger"
          ? "bg-[#fee9e5] text-[#9a4129]"
          : "bg-sand text-slate";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${toneClass}`}>
      {children}
    </span>
  );
}


function uniqueStrings(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort();
}


function compareDocuments(left: DocumentItem, right: DocumentItem, sort: DocumentSort): number {
  if (sort === "title_asc") {
    return left.title.localeCompare(right.title);
  }
  if (sort === "chunks_desc") {
    return right.chunk_count - left.chunk_count || compareDateValues(right.updated_at, left.updated_at);
  }
  if (sort === "effective_desc") {
    return compareNullableDates(right.effective_date, left.effective_date) || compareDateValues(right.updated_at, left.updated_at);
  }
  return compareDateValues(right.updated_at, left.updated_at);
}


function compareDateValues(left: string | null, right: string | null): number {
  const leftTime = left ? new Date(left).getTime() : 0;
  const rightTime = right ? new Date(right).getTime() : 0;
  return leftTime - rightTime;
}


function compareNullableDates(left: string | null, right: string | null): number {
  if (!left && !right) {
    return 0;
  }
  if (!left) {
    return -1;
  }
  if (!right) {
    return 1;
  }
  return compareDateValues(left, right);
}


function buildPagination(currentPage: number, totalPages: number): Array<number | "ellipsis"> {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  const pages = new Set<number>([1, totalPages, currentPage, currentPage - 1, currentPage + 1]);
  const normalized = Array.from(pages)
    .filter((page) => page >= 1 && page <= totalPages)
    .sort((left, right) => left - right);

  const result: Array<number | "ellipsis"> = [];
  for (let index = 0; index < normalized.length; index += 1) {
    const page = normalized[index];
    const previous = normalized[index - 1];
    if (previous && page - previous > 1) {
      result.push("ellipsis");
    }
    result.push(page);
  }
  return result;
}


function formatDate(value: string | null): string {
  if (!value) {
    return "Not set";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}


function readableLabel(value: string): string {
  return value.replaceAll("_", " ");
}


function truncateText(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 3).trimEnd()}...`;
}


function statusTone(status: string): "neutral" | "success" | "warning" | "danger" {
  if (status === "indexed") {
    return "success";
  }
  if (status === "uploaded" || status === "draft") {
    return "warning";
  }
  if (status === "failed") {
    return "danger";
  }
  return "neutral";
}


function confidenceTone(confidence: "high" | "medium" | "low"): "success" | "warning" | "danger" {
  if (confidence === "high") {
    return "success";
  }
  if (confidence === "medium") {
    return "warning";
  }
  return "danger";
}


function formatSortLabel(value: string): string {
  if (value === "updated_desc") {
    return "Newest Update";
  }
  if (value === "title_asc") {
    return "Title A-Z";
  }
  if (value === "chunks_desc") {
    return "Most Chunks";
  }
  if (value === "effective_desc") {
    return "Latest Effective";
  }
  return readableLabel(value);
}
