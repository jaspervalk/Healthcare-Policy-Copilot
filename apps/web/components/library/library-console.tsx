"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Banner } from "@/components/ui/banner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { api } from "@/lib/api";
import type { DocumentItem } from "@/lib/types";


export function LibraryConsole() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DocumentItem | null>(null);
  const [editTarget, setEditTarget] = useState<DocumentItem | null>(null);
  const [showUpload, setShowUpload] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setIsLoading(true);
    try {
      setDocuments(await api.listDocuments());
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load documents.");
    } finally {
      setIsLoading(false);
    }
  }

  const statusOptions = useMemo(() => {
    return Array.from(new Set(documents.map((document) => document.ingestion_status))).sort();
  }, [documents]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return documents
      .filter((document) => {
        if (statusFilter !== "all" && document.ingestion_status !== statusFilter) {
          return false;
        }
        if (!query) {
          return true;
        }
        const haystack = [
          document.title,
          document.source_filename,
          document.document_type ?? "",
          document.department ?? "",
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(query);
      })
      .sort((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());
  }, [documents, search, statusFilter]);

  const indexedCount = documents.filter((document) => document.ingestion_status === "indexed").length;
  const failedCount = documents.filter((document) => document.ingestion_status === "failed").length;

  async function handleReindex(document: DocumentItem) {
    setBusyId(document.id);
    setMessage(null);
    setError(null);
    try {
      const result = await api.reindexDocument(document.id);
      setMessage(`Reindexed ${result.chunk_count} chunk${result.chunk_count === 1 ? "" : "s"} from ${result.document.title}.`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Reindex failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete(target: DocumentItem) {
    setBusyId(target.id);
    setMessage(null);
    setError(null);
    try {
      const result = await api.deleteDocument(target.id);
      setMessage(`Deleted ${result.title}.`);
      setDocuments((current) => current.filter((document) => document.id !== result.document_id));
      setDeleteTarget(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Delete failed.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-ink-900">Library</h1>
          <p className="mt-1 text-sm text-ink-500">
            {documents.length} document{documents.length === 1 ? "" : "s"} · {indexedCount} indexed
            {failedCount > 0 ? ` · ${failedCount} failed` : ""}
          </p>
        </div>
        <Button onClick={() => setShowUpload(true)}>Upload PDF</Button>
      </header>

      {message ? <Banner tone="success" className="mb-3">{message}</Banner> : null}
      {error ? <Banner tone="danger" className="mb-3">{error}</Banner> : null}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search title or filename"
          className="h-9 w-64 rounded-md border border-ink-200 bg-white px-3 text-sm text-ink-800 placeholder:text-ink-400 focus:border-primary-500 focus:outline-none"
        />
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value)}
          className="h-9 rounded-md border border-ink-200 bg-white px-2 text-sm text-ink-800"
        >
          <option value="all">All statuses</option>
          {statusOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-hidden rounded-lg border border-ink-100 bg-white">
        {isLoading && documents.length === 0 ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="h-12 animate-pulse rounded-md bg-ink-50" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-12">
            <EmptyState
              title={documents.length === 0 ? "Empty library" : "No documents match"}
              description={
                documents.length === 0
                  ? "Upload a policy PDF to begin building the corpus."
                  : "Adjust the search or status filter."
              }
              action={documents.length === 0 ? <Button onClick={() => setShowUpload(true)}>Upload PDF</Button> : null}
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-ink-50/60 text-xs uppercase tracking-wide text-ink-500">
                <tr>
                  <th className="px-4 py-2 text-left font-medium">Document</th>
                  <th className="px-4 py-2 text-left font-medium">Status</th>
                  <th className="px-4 py-2 text-left font-medium">Type</th>
                  <th className="px-4 py-2 text-right font-medium">Chunks</th>
                  <th className="px-4 py-2 text-right font-medium">Updated</th>
                  <th className="px-4 py-2 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-100">
                {filtered.map((document) => (
                  <DocumentRow
                    key={document.id}
                    document={document}
                    busy={busyId === document.id}
                    onEdit={() => setEditTarget(document)}
                    onReindex={() => handleReindex(document)}
                    onDelete={() => setDeleteTarget(document)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showUpload ? (
        <UploadDialog
          onClose={() => setShowUpload(false)}
          onUploaded={async (uploaded) => {
            setMessage(
              `Indexed ${uploaded.chunk_count} chunk${uploaded.chunk_count === 1 ? "" : "s"} from ${uploaded.document.title}.`,
            );
            setShowUpload(false);
            await load();
          }}
          onError={(message) => setError(message)}
        />
      ) : null}

      {deleteTarget ? (
        <DeleteDialog
          document={deleteTarget}
          isDeleting={busyId === deleteTarget.id}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => handleDelete(deleteTarget)}
        />
      ) : null}

      {editTarget ? (
        <EditDialog
          document={editTarget}
          onCancel={() => setEditTarget(null)}
          onSaved={async (updated) => {
            setMessage(`Saved metadata for ${updated.title}.`);
            setEditTarget(null);
            await load();
          }}
          onError={(detail) => setError(detail)}
        />
      ) : null}
    </div>
  );
}


function DocumentRow({
  document,
  busy,
  onEdit,
  onReindex,
  onDelete,
}: {
  document: DocumentItem;
  busy: boolean;
  onEdit: () => void;
  onReindex: () => void;
  onDelete: () => void;
}) {
  return (
    <tr className="hover:bg-ink-50/50">
      <td className="max-w-md px-4 py-3">
        <p className="truncate font-medium text-ink-900">{document.title}</p>
        <p className="truncate text-xs text-ink-400">{document.source_filename}</p>
      </td>
      <td className="px-4 py-3">
        <Badge tone={statusTone(document.ingestion_status)}>{document.ingestion_status}</Badge>
        {document.parse_error ? (
          <p className="mt-1 max-w-xs truncate text-xs text-rose-600">{document.parse_error}</p>
        ) : null}
      </td>
      <td className="px-4 py-3 text-ink-600">
        {document.document_type ?? <span className="text-ink-400">—</span>}
      </td>
      <td className="px-4 py-3 text-right tabular-nums text-ink-600">{document.chunk_count}</td>
      <td className="px-4 py-3 text-right text-ink-500">{formatDate(document.updated_at)}</td>
      <td className="px-4 py-3 text-right">
        <div className="flex justify-end gap-1.5">
          <Button size="sm" variant="ghost" onClick={onEdit} disabled={busy}>
            Edit
          </Button>
          <Button size="sm" variant="secondary" onClick={onReindex} disabled={busy}>
            {busy ? "Working…" : "Reindex"}
          </Button>
          <Button size="sm" variant="ghost" onClick={onDelete} disabled={busy}>
            Delete
          </Button>
        </div>
      </td>
    </tr>
  );
}


type EditableField =
  | "title"
  | "document_type"
  | "department"
  | "policy_status"
  | "version_label"
  | "effective_date"
  | "review_date";

function EditDialog({
  document,
  onCancel,
  onSaved,
  onError,
}: {
  document: DocumentItem;
  onCancel: () => void;
  onSaved: (updated: DocumentItem) => void;
  onError: (detail: string) => void;
}) {
  const [form, setForm] = useState({
    title: document.title ?? "",
    document_type: document.document_type ?? "",
    department: document.department ?? "",
    policy_status: document.policy_status ?? "",
    version_label: document.version_label ?? "",
    effective_date: document.effective_date ?? "",
    review_date: document.review_date ?? "",
  });
  const [submitting, setSubmitting] = useState(false);

  function update<K extends EditableField>(key: K, value: string) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function dirtyPayload() {
    const initial = {
      title: document.title ?? "",
      document_type: document.document_type ?? "",
      department: document.department ?? "",
      policy_status: document.policy_status ?? "",
      version_label: document.version_label ?? "",
      effective_date: document.effective_date ?? "",
      review_date: document.review_date ?? "",
    };
    const payload: Record<string, string | null> = {};
    (Object.keys(initial) as EditableField[]).forEach((key) => {
      const next = form[key];
      if (next !== initial[key]) {
        payload[key] = next === "" ? null : next;
      }
    });
    return payload;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = dirtyPayload();
    if (Object.keys(payload).length === 0) {
      onCancel();
      return;
    }
    setSubmitting(true);
    try {
      const updated = await api.patchDocument(document.id, payload);
      onSaved(updated);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Save failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-40 flex items-center justify-center px-4">
      <button type="button" aria-label="Close" onClick={onCancel} className="absolute inset-0 bg-ink-900/30 backdrop-blur-sm" />
      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-lg rounded-lg border border-ink-100 bg-white p-5 shadow-lift"
      >
        <h2 className="font-display text-lg font-semibold text-ink-900">Edit metadata</h2>
        <p className="mt-1 text-sm text-ink-500">
          Manual values survive reindexing. Leave a field blank to clear it back to detection.
        </p>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <FormField label="Title" wide>
            <input
              type="text"
              value={form.title}
              onChange={(event) => update("title", event.target.value)}
              className={inputClass}
            />
          </FormField>
          <FormField label="Document type">
            <input
              type="text"
              value={form.document_type}
              onChange={(event) => update("document_type", event.target.value)}
              placeholder="policy / procedure / manual / guideline"
              className={inputClass}
            />
          </FormField>
          <FormField label="Department">
            <input
              type="text"
              value={form.department}
              onChange={(event) => update("department", event.target.value)}
              placeholder="utilization_management"
              className={inputClass}
            />
          </FormField>
          <FormField label="Policy status">
            <select
              value={form.policy_status}
              onChange={(event) => update("policy_status", event.target.value)}
              className={inputClass}
            >
              <option value="">— unset —</option>
              <option value="active">active</option>
              <option value="draft">draft</option>
              <option value="retired">retired</option>
            </select>
          </FormField>
          <FormField label="Version">
            <input
              type="text"
              value={form.version_label}
              onChange={(event) => update("version_label", event.target.value)}
              className={inputClass}
            />
          </FormField>
          <FormField label="Effective date">
            <input
              type="date"
              value={form.effective_date}
              onChange={(event) => update("effective_date", event.target.value)}
              className={inputClass}
            />
          </FormField>
          <FormField label="Review date">
            <input
              type="date"
              value={form.review_date}
              onChange={(event) => update("review_date", event.target.value)}
              className={inputClass}
            />
          </FormField>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Saving…" : "Save"}
          </Button>
        </div>
      </form>
    </div>
  );
}


const inputClass =
  "h-9 w-full rounded-md border border-ink-200 bg-white px-2.5 text-sm text-ink-800 placeholder:text-ink-400 focus:border-primary-500 focus:outline-none";


function FormField({
  label,
  wide = false,
  children,
}: {
  label: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className={`block text-sm ${wide ? "sm:col-span-2" : ""}`}>
      <span className="mb-1 block text-xs font-medium text-ink-500">{label}</span>
      {children}
    </label>
  );
}


function UploadDialog({
  onClose,
  onUploaded,
  onError,
}: {
  onClose: () => void;
  onUploaded: (uploaded: Awaited<ReturnType<typeof api.uploadDocument>>) => void;
  onError: (message: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      return;
    }
    setSubmitting(true);
    try {
      const uploaded = await api.uploadDocument(file);
      onUploaded(uploaded);
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Upload failed.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-40 flex items-center justify-center px-4">
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 bg-ink-900/30 backdrop-blur-sm" />
      <form
        onSubmit={handleSubmit}
        className="relative w-full max-w-md rounded-lg border border-ink-100 bg-white p-5 shadow-lift"
      >
        <h2 className="font-display text-lg font-semibold text-ink-900">Upload PDF</h2>
        <p className="mt-1 text-sm text-ink-500">Adds the document to the corpus and indexes it immediately.</p>

        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="mt-4 flex w-full items-center justify-between rounded-md border border-dashed border-ink-200 bg-ink-50/40 px-4 py-3 text-left text-sm hover:border-ink-300"
        >
          <span className="text-ink-700">{file ? file.name : "Choose a file"}</span>
          <span className="text-xs text-ink-400">{file ? formatSize(file.size) : "PDF only"}</span>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          className="hidden"
        />

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={!file || submitting}>
            {submitting ? "Uploading…" : "Upload & Index"}
          </Button>
        </div>
      </form>
    </div>
  );
}


function DeleteDialog({
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
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <button type="button" aria-label="Close" onClick={onCancel} className="absolute inset-0 bg-ink-900/35" />
      <div className="relative w-full max-w-md rounded-lg border border-ink-100 bg-white p-5 shadow-lift">
        <h2 className="font-display text-lg font-semibold text-ink-900">Delete document?</h2>
        <p className="mt-2 text-sm text-ink-600">
          This permanently removes <span className="font-medium text-ink-900">{document.title}</span> from the corpus,
          vector index, and stored files.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={isDeleting}>
            Cancel
          </Button>
          <Button variant="danger" onClick={onConfirm} disabled={isDeleting}>
            {isDeleting ? "Deleting…" : "Delete"}
          </Button>
        </div>
      </div>
    </div>
  );
}


function statusTone(status: string): "neutral" | "success" | "warning" | "danger" {
  if (status === "indexed") return "success";
  if (status === "failed") return "danger";
  if (status === "uploaded") return "warning";
  return "neutral";
}


function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(value));
}


function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
