# Backend Changes — Working Notes

Running summary of in-progress backend rework. Driven by `BACKEND_AUDIT.md` Top-5 list.
Each phase corresponds to one Top-5 item.

---

## Phase 1 — Citation integrity + evidence-derived confidence

**Closed:** Audit C1 (fabricated citations), H2 (model-self-reported confidence).

### What changed
- Removed the `_fallback_citations` decoration on the model path. When the model returns no citations or sets `abstained=True`, the response now carries `citations=[]`, `abstained=True`, `confidence="low"`. No more synthetic citations attached to abstained answers.
- Added `evidence_confidence(citations, retrieved_chunks)` (pure function, module-level) that derives a bucket from: top retrieval score, score margin, citation count, unique source documents, and whether all cited chunks have `policy_status == "active"`.
- Added `combine_confidence(model_bucket, evidence_bucket)` returning the minimum of the two ranks. The model can only ever downgrade itself, never inflate above what evidence supports.
- Final response includes a new `confidence_inputs: ConfidenceInputs` field exposing the raw signals so the UI/eval layer can explain the rating.
- `policy_status` now flows from Qdrant payload through `QueryChunkResult` to enable the active-status check.
- Fallback (no-API-key) path: chatty preamble removed, single honest citation, confidence derived from evidence (was hardcoded `"medium"`).

### Files
[apps/api/app/services/answering.py](apps/api/app/services/answering.py),
[apps/api/app/services/retrieval.py](apps/api/app/services/retrieval.py),
[apps/api/app/schemas.py](apps/api/app/schemas.py),
[apps/api/tests/test_answering.py](apps/api/tests/test_answering.py).

### How to verify
- Ask a question whose evidence is weak (low retrieval scores). Confidence should report `low` even if the model self-reports high.
- Ask an out-of-corpus question. Response: `abstained=true`, `citations=[]`, `confidence_reasons` explains why.

---

## Phase 2 — Atomic ingestion + embedding provider stamp + Qdrant singleton

**Closed:** Audit C2 (silent embedder fallback), C3 (per-request QdrantClient against embedded local store), C4 (non-atomic SQL+Qdrant indexing), H8 (Qdrant errors swallowed in search), M8 (no collection stamp).

### What changed
- **Strict embeddings.** When `OPENAI_API_KEY` is configured, OpenAI failures now raise `EmbeddingError` instead of silently falling back to `LocalHashingEmbedder`. The local-hash path is reserved for the no-key case only. `EmbeddingBatch` carries explicit `provider` and `model` fields.
- **Collection stamp.** New `index_collections` SQL table records `(name, provider, model, dimensions)`. On every ingest the stamp is read; mismatches against the current embedder raise `StampMismatchError` *before* any SQL or Qdrant write. On a clean ingest the stamp is written/updated.
- **Atomic ingest pipeline.** `index_document` reordered: parse → chunk → embed entirely in memory before any persistence. SQL writes happen inside a session that is only committed after the Qdrant upsert succeeds. On Qdrant failure we `db.rollback()` and best-effort scrub any partial Qdrant points. On commit failure after a successful Qdrant upsert we revert Qdrant.
- **Single shared QdrantClient.** Process-wide singleton via `get_qdrant_client()` / `close_qdrant_client()`. The embedded local store no longer gets multiple clients fighting over the lockfile. Lifespan warms it on startup, closes on shutdown.
- **Search no longer swallows exceptions.** Qdrant transport errors propagate instead of returning `[]` and looking like "no evidence."

### Files
[apps/api/app/services/embeddings.py](apps/api/app/services/embeddings.py),
[apps/api/app/services/qdrant_index.py](apps/api/app/services/qdrant_index.py),
[apps/api/app/services/index_stamp.py](apps/api/app/services/index_stamp.py),
[apps/api/app/services/documents.py](apps/api/app/services/documents.py),
[apps/api/app/models.py](apps/api/app/models.py),
[apps/api/app/main.py](apps/api/app/main.py),
[apps/api/tests/test_embeddings.py](apps/api/tests/test_embeddings.py),
[apps/api/tests/test_index_stamp.py](apps/api/tests/test_index_stamp.py),
[apps/api/tests/test_indexing.py](apps/api/tests/test_indexing.py),
[apps/api/tests/conftest.py](apps/api/tests/conftest.py).

### How to verify
- After wiping `data/qdrant/*` and `data/app.db`, upload a PDF. Inspect SQLite: `index_collections` row exists with the current embedder.
- Change `OPENAI_EMBEDDING_MODEL` in `.env` and try to ingest a new PDF. Should fail with `StampMismatchError` and not write anything.
- Stop the API mid-ingest (or simulate Qdrant down). SQLite must contain the document at its previous state, not a partial reindex.

### Operational note
The previous dev DB was already corrupt (5 SQL docs, 167 chunks, 3 Qdrant points at 256-dim hash vectors). Wipe + reupload was required before this code is exercised against real data:
```bash
rm -rf data/qdrant/* data/app.db data/processed/* data/raw/*
```

---

## Phase 3 — Evaluation harness

**Closed:** Audit H1 (no eval data, no eval infrastructure).

### What changed
- New `app/eval/` package:
  - `dataset.py` — JSONL loader. Resolves bundled dataset names (e.g. `"medicare_starter"`) to `app/eval/datasets/<name>.jsonl`, or accepts an absolute path.
  - `metrics.py` — pure functions: `recall_at_k_for_documents`, `mrr_for_documents`, `citation_correctness`, `case_metrics`, `aggregate_metrics`. Document-level grounding by `source_filename` (stable across reindex; chunk UUIDs aren't). Abstention cases skip retrieval/citation metrics — only `abstain_correct` is scored.
  - `judge.py` — LLM-as-judge groundedness scorer using the Responses API with a `JudgeDraft` schema (verdict + 1-5 score + reasoning). Skips gracefully when no API key.
  - `runner.py` — orchestrates retrieval → answer → metric computation → persist. Computes a `config_hash` over `(dataset, top_k, embedding provider/model/dim, answer model, judge enabled)` so runs can be diffed across ablations.
- New SQL tables `eval_runs` and `eval_cases` capturing every retrieval + answer + metric per case, plus an aggregate snapshot per run.
- New endpoints: `POST /api/evals/run`, `GET /api/evals`, `GET /api/evals/{id}`.
- Starter dataset: 31 cases across 8 categories (direct_lookup, multi_hop, version_sensitive, ambiguous, abstention, near_miss_wording, acronym_heavy, comparison) targeting the indexed Medicare Benefit Policy Manual chapters 1–3 + Medicare General Information ch 1.

### Files
[apps/api/app/eval/](apps/api/app/eval/),
[apps/api/app/api/routes/evals.py](apps/api/app/api/routes/evals.py),
[apps/api/app/api/router.py](apps/api/app/api/router.py),
[apps/api/app/models.py](apps/api/app/models.py),
[apps/api/app/schemas.py](apps/api/app/schemas.py),
[apps/api/tests/test_eval_metrics.py](apps/api/tests/test_eval_metrics.py),
[apps/api/tests/test_eval_runner.py](apps/api/tests/test_eval_runner.py).

### How to verify
With the corpus reuploaded:
```bash
curl -X POST http://localhost:8000/api/evals/run \
  -H 'Content-Type: application/json' \
  -d '{"dataset":"medicare_starter","name":"baseline","top_k":5,"judge":true}'
```

Lists: `GET /api/evals`. Detail: `GET /api/evals/{id}` (includes per-case retrieved chunks, citations, metrics, judge verdict).

### Caveat on the dataset
Ground truth (`expected_documents` per case) was inferred from chapter titles, not from reading every PDF end-to-end. Treat the first run as a debugging tool: where a case scores `recall_at_k=0` but the retrieved chunk is clearly correct, fix that case's `expected_documents` and re-run. The harness is the deliverable; the dataset iterates. Same `id` values across edits keep runs comparable.

---

## Phase 4 — Structured query/answer logging

**Closed:** Audit H4 (no observability), L2 (no request IDs).

### What changed
- New `query_logs` SQL table — one row per `/api/query` or `/api/answer` request, success or failure. Captures: `request_id`, `endpoint`, `question`, `filters`, `top_k`, retrieved chunk_ids/documents/scores, `embedding_provider`, `answer_model`, `abstained`, `confidence`, `confidence_inputs`, citations (chunk_id + source_filename pairs), `token_usage`, `latency_ms`, `status`, `error`, `created_at` (indexed for ordering).
- Request-ID middleware in `main.py`. Every response carries `X-Request-ID`; if the caller sent one, it's preserved, otherwise a UUID is generated. Persisted on the log row so logs and external traces can be joined.
- `app/services/query_logs.py` helpers (`log_query`, `log_answer`, `log_failure`) persist on a fresh `SessionLocal()` — logging cannot poison the request's transaction. All persistence failures are swallowed and logged via `logger.exception`.
- Token usage extracted from the OpenAI Responses API via `_extract_token_usage` (defensive across SDK field-name variations) and surfaced on `AnswerResponse.token_usage`.
- New endpoints: `GET /api/queries` (paginated via `?limit=&offset=`, default 100), `GET /api/queries/{id}` (full detail).
- `/api/query` and `/api/answer` rewritten to log on both happy and error paths, with latency measured in `time.perf_counter()`.

### Files
[apps/api/app/models.py](apps/api/app/models.py),
[apps/api/app/schemas.py](apps/api/app/schemas.py),
[apps/api/app/main.py](apps/api/app/main.py),
[apps/api/app/services/query_logs.py](apps/api/app/services/query_logs.py),
[apps/api/app/services/answering.py](apps/api/app/services/answering.py),
[apps/api/app/api/routes/query.py](apps/api/app/api/routes/query.py),
[apps/api/app/api/routes/queries.py](apps/api/app/api/routes/queries.py),
[apps/api/app/api/router.py](apps/api/app/api/router.py),
[apps/api/tests/test_query_logs.py](apps/api/tests/test_query_logs.py).

### How to verify
After hitting `/api/query` or `/api/answer` once:
```
curl http://localhost:8000/api/queries?limit=10
curl http://localhost:8000/api/queries/{log_id}
```
Inspect `X-Request-ID` in any response header. Force an error (e.g. send a question while Qdrant is offline) and confirm a `status="error"` row lands in the log.

---

## Phase 5 — API hygiene

**Closed:** Audit H3 (errors squashed to 400), H5 (no upload safety), M3 (checksum dedup unused), M9 (no PATCH to fix metadata), L1 (loose CORS — partly: stays loose for dev, but admin auth now gates destructive routes).

### What changed
- **Centralized exception → HTTP mapping** in `app/api/errors.py`. Replaces the project-wide `except Exception → HTTPException(400, str(exc))` pattern. Mapping:
  - `ValueError`, `InvalidPdfError`, `DatasetError` → 400
  - `DuplicateDocumentError`, `StampMismatchError` → 409 (with `existing_document_id` on duplicates)
  - `FileTooLargeError` → 413
  - `EmbeddingError` → 502 with sanitized detail (raw provider error never leaks)
  - `FileNotFoundError` → 404, `PermissionError` → 403
  - Anything else → 500 with `"Internal error. See server logs for details."`; full traceback goes to `logger.exception`.
  - Existing `HTTPException` instances pass through untouched.
- **Upload safety** (`app/services/upload_safety.py`):
  - `MAX_UPLOAD_SIZE_BYTES` setting (default 50 MB) — refused before any disk write.
  - Magic-byte check: bytes must start with `%PDF-`. Rejecting non-PDFs upfront avoids surfacing pypdf internal errors as 400s.
- **Checksum-based dedup.** `find_document_by_checksum` is now called inside `create_document_from_upload`. Re-uploading the same file returns 409 with the existing document id and title in `detail` instead of poisoning the corpus with duplicates.
- **`PATCH /documents/{id}`** — partial update over a whitelist (`title`, `document_type`, `department`, `policy_status`, `version_label`, `effective_date`, `review_date`). Existing `index_document` heuristics already preserve non-None manual values via `document.X = document.X or _detect_X(...)`, so PATCH-then-reindex is the override path.
- **Optional admin auth** (`app/api/auth.py`). When `ADMIN_TOKEN` env is set, `DELETE /documents/{id}` and `PATCH /documents/{id}` require `Authorization: Bearer <token>`. When unset, both routes stay open for local dev.
- All four route modules (`documents`, `query`, `evals`) now route their `except Exception` through `map_exception(...)`.

### Files
[apps/api/app/core/config.py](apps/api/app/core/config.py),
[apps/api/app/api/errors.py](apps/api/app/api/errors.py),
[apps/api/app/api/auth.py](apps/api/app/api/auth.py),
[apps/api/app/services/upload_safety.py](apps/api/app/services/upload_safety.py),
[apps/api/app/services/documents.py](apps/api/app/services/documents.py),
[apps/api/app/api/routes/documents.py](apps/api/app/api/routes/documents.py),
[apps/api/app/api/routes/query.py](apps/api/app/api/routes/query.py),
[apps/api/app/api/routes/evals.py](apps/api/app/api/routes/evals.py),
[apps/api/app/schemas.py](apps/api/app/schemas.py),
[.env.example](.env.example),
plus tests:
[test_upload_safety.py](apps/api/tests/test_upload_safety.py),
[test_errors.py](apps/api/tests/test_errors.py),
[test_documents_api.py](apps/api/tests/test_documents_api.py),
[test_auth.py](apps/api/tests/test_auth.py).

### How to verify
- Upload a non-PDF (e.g. rename a `.zip`) → 400 with magic-byte message.
- Upload a >50MB PDF → 413.
- Upload the same PDF twice → 409 with `existing_document_id`.
- `PATCH /api/documents/{id}` with `{"policy_status":"draft"}` → updated row; reindex preserves the manual value.
- Set `ADMIN_TOKEN=secret` in `.env`, restart, call `DELETE /api/documents/{id}` without header → 401.
- Trigger an `EmbeddingError` (e.g. wrong API key) on `/api/answer` → 502 with sanitized message; original error is in server logs only.

---

## Phase 6 — Hybrid retrieval (BM25 + dense via RRF)

**Closed:** Audit M5 (no score threshold / no diversity) — partly addressed via fusion; the dense-only weakness called out in the audit's retrieval-quality section is now resolvable per-query.

### What changed
- **In-memory BM25 sparse index** in `app/services/hybrid_index.py`. Keyed by chunk_id over `chunk.normalized_text`, built from SQL chunks where `Document.ingestion_status == "indexed"`. Process-wide singleton; built lazily, refreshed after every successful ingest/reindex/delete and warmed at lifespan startup. Tokenizer drops basic English stopwords and non-alphanumeric noise. Added `rank_bm25` to `requirements.txt`.
- **RRF fusion** (`rrf_fuse(dense, sparse, k=60)`). Each ranker contributes `1 / (k + rank)`; only positions matter, scores are score-scale-agnostic.
- **Mode-aware retrieval.** `RetrievalService.search(..., mode="dense"|"hybrid")`:
  - `dense`: previous behavior, single Qdrant call.
  - `hybrid`: dense top-30 + sparse top-30, fused, top-K returned. Sparse-only chunks have their payloads resolved via a Qdrant `retrieve(ids=...)` lookup; their `score` is floored to `0.0` since dense never saw them within the over-fetch window — confidence calibration stays honest, sparse-supplied chunks won't inflate the bucket.
  - When the caller passes `filters`, sparse-only candidates that didn't pass the filtered dense search are dropped: the BM25 index is filter-unaware, and we don't want a filtered query to silently widen its scope.
  - When the sparse index is empty (no docs indexed yet), hybrid falls back cleanly to dense-only.
- **`retrieval_mode` field** on `QueryRequest`, `AnswerRequest`, and `EvalRunRequest` (default `"hybrid"`). Threaded through `AnsweringService.answer`, the eval `RunOptions`, and the eval `config_snapshot` so dense vs hybrid runs produce *different* `config_hash`es and can be diffed in `GET /api/evals`.

### Files
[apps/api/app/services/hybrid_index.py](apps/api/app/services/hybrid_index.py),
[apps/api/app/services/retrieval.py](apps/api/app/services/retrieval.py),
[apps/api/app/services/answering.py](apps/api/app/services/answering.py),
[apps/api/app/services/documents.py](apps/api/app/services/documents.py),
[apps/api/app/main.py](apps/api/app/main.py),
[apps/api/app/schemas.py](apps/api/app/schemas.py),
[apps/api/app/api/routes/query.py](apps/api/app/api/routes/query.py),
[apps/api/app/api/routes/evals.py](apps/api/app/api/routes/evals.py),
[apps/api/app/eval/runner.py](apps/api/app/eval/runner.py),
[apps/api/requirements.txt](apps/api/requirements.txt),
[apps/api/tests/test_hybrid_index.py](apps/api/tests/test_hybrid_index.py),
[apps/api/tests/test_retrieval.py](apps/api/tests/test_retrieval.py),
plus stub-signature updates in test_answering.py and test_eval_runner.py.

### How to verify
With the corpus reuploaded:
```
# Baseline (dense)
curl -X POST http://localhost:8000/api/evals/run \
  -H 'Content-Type: application/json' \
  -d '{"dataset":"medicare_starter","name":"dense-baseline","retrieval_mode":"dense","judge":true}'

# Hybrid
curl -X POST http://localhost:8000/api/evals/run \
  -H 'Content-Type: application/json' \
  -d '{"dataset":"medicare_starter","name":"hybrid","retrieval_mode":"hybrid","judge":true}'

curl http://localhost:8000/api/evals
```
Two runs with different `config_hash` values, comparable `recall_at_k_mean` / `mrr_mean` / `judge_score_mean`. The honest dense-vs-hybrid number is in the diff.

### Trade-offs
- BM25 is recomputed in-memory at startup and after every corpus change. Fine at portfolio scale (tens of docs). Not a streaming index — updates take O(corpus) per change.
- Filter awareness is approximate: sparse-only candidates are silently dropped when the query carries filters. This is conservative (preserves filter intent) but means hybrid gives up some keyword recall on filtered queries. Worth revisiting if eval shows it matters.
- RRF `k=60` is the conventional default; not tuned. The eval harness can drive that decision later.

---

## Phase 7 — Heuristic metadata fixes

**Closed:** Audit H7.

### What changed
- **`_detect_document_type`** no longer returns the first dict-order match. It scores each label by word-boundary keyword matches and picks the highest. A "Care Management Procedure" PDF that mentions "policy" once now correctly classifies as `procedure`. Empty signal returns `None`.
- **`_detect_department`** got the same scoring treatment for consistency.
- **`_score_keywords`** uses `\b` word boundaries — "policymaker" no longer counts as a "policy" hit.
- **`_detect_policy_status`** no longer defaults to `"active"` on every document. With no signal, it returns `None` ("unknown"). Active is only claimed when the text actually contains `active`/`effective`/`current` as a word. `retired`/`superseded` and `draft` keep precedence over `active` when both appear. `Document.policy_status` was already nullable in SQL — no schema change needed.

### Files
[apps/api/app/services/documents.py](apps/api/app/services/documents.py),
[apps/api/tests/test_documents.py](apps/api/tests/test_documents.py).

### How to verify
The new tests reproduce the audit's exact failure modes (procedure mis-tagged as policy; "policymaker" matching "policy"; default-active without evidence) and assert the fixed behavior.

---

## Test suite snapshot

82 tests, all passing.
- `test_answering` (11): citation/confidence behavior, evidence buckets, model-vs-evidence combination.
- `test_chunking` (1), `test_documents` (1), `test_document_deletion` (1): pre-existing.
- `test_embeddings` (3): strict provider, no silent fallback.
- `test_index_stamp` (6): stamp validation, write/read, mismatch rejection.
- `test_indexing` (3): SQL rollback on Qdrant failure, stamp written on success, stamp mismatch blocks before any write.
- `test_eval_metrics` (10): recall, mrr, citation correctness, abstention skip, aggregation.
- `test_eval_runner` (1): end-to-end run persistence + config_hash determinism.
- `test_query_logs` (5): success/failure persistence, ordering, token-usage roundtrip, swallow-on-persist-failure.
- `test_upload_safety` (4): magic-byte and size-cap behavior.
- `test_errors` (9): every branch of the exception → HTTP mapper, including 5xx detail sanitization.
- `test_documents_api` (4): checksum dedup lookup and PATCH whitelist.
- `test_auth` (5): admin token enabled/disabled paths.
- `test_hybrid_index` (6): tokenizer, status filter, ranking, RRF.
- `test_retrieval` (4): dense-only mode, hybrid fusion, empty-sparse fallback, filter-aware sparse drop.
- `test_documents` (9): expanded coverage of the metadata heuristics including the audit's H7 reproductions.

---

## Audit status after Phases 1–7

| Tier | Closed | Open |
|---|---|---|
| Critical | C1, C2, C3, C4 | — |
| High | H1, H2, H3, H4, H5, H7, H8 | H6 |
| Medium | M3, M5, M8, M9 | M1, M2, M4, M6, M7, M10, M11, M12, M13 |
| Low | L2 | L1, L3, L4, L5, L6 |

Remaining backlog ranked by portfolio signal:
- **Service DI cleanup** (H6): inject `QdrantClient`, `EmbeddingService`, `DB session` into services rather than constructing in `__init__`. Mostly a testability win; the conftest already isolates the only real-world fallout.
- **Async indexing** (M7): move ingestion off the request thread; switch upload to 202 + status polling. Honest for production, more boilerplate than signal at portfolio scale.
- **Alembic migrations** (M11): becomes mandatory once anyone runs the project against a database with prior data.
- **Smaller cleanups**: M1 (`token_count` → `word_count`), M2 (relative `stored_path`), M6 (Title Case heading detection), M10 (deterministic chunk IDs), M12, M13 (Qdrant payload staleness on metadata edit).

---

# Frontend phases

## Phase F1 + F2 — Reset, routing, Q&A workspace with inline citations

### Visual reset
- Replaced the system-font stack (Trebuchet MS as display) with **Inter** (body) and **Fraunces** (display) loaded via `next/font/google`.
- Reduced the corner-radius zoo (9 distinct values) to a 5-step scale (`sm 6px`, `DEFAULT 10px`, `md 12px`, `lg 16px`, `xl 20px`).
- Replaced the ad-hoc palette with an `ink` ramp (50–900) plus `accent` (former clay, demoted to status) and `sage` (former moss, demoted to subtle text). One primary action color: `ink-800`.
- Stripped the triple-stacked HTML/body gradient + grid texture down to one calm `surface` background.
- Single `Badge`, single `Button` with four real variants (primary / secondary / ghost / danger), single `Banner`, single `EmptyState`. No more `MetricCard` / `TopMetric` / `MiniNote` / `InfoLine` / `InfoRow` proliferation.

### Routing
- Removed the marketing hero from `app/page.tsx`. No more capability pills, status cards, hero copy.
- Split the single 2003-line `phase-one-console.tsx` into four routes with a shared `AppShell`:
  - `/` — Q&A workspace (home).
  - `/library` — corpus management.
  - `/evals` — eval dashboard surfacing the Phase 3 backend (runs list + per-run metrics + per-case table).
  - `/queries` — query log feed surfacing the Phase 4 backend (filterable list + per-row drill-in).
- Top nav with four items, sticky, no decorative chrome. Path alias `@/*` configured in `tsconfig.json` for clean imports.

### Q&A workspace (the killer feature)
- Single composer: textarea + three filter chips (department / type / status) + `dense | hybrid` mode toggle + primary "Ask" button. No "Workflow Scope" sidebar, no metric tiles above, no "Question Composer" eyebrow. ⌘+Enter to submit.
- **Inline citation markers** in the answer text. `[1]`, `[2]`, `[3]` rendered at sentence boundaries; clicking a marker highlights and scrolls the corresponding evidence row. The previous detached "Citations" + "Evidence Explorer" + "Selected Evidence" three-panel duplication is gone — there is now one canonical Evidence panel beside the answer.
- `ConfidenceChip` exposes the Phase 1 `confidence_inputs` (top score, score margin, citation count, source documents, all-cited-active, evidence bucket) on click — first time these signals are visible to a user.
- `AnswerMeta` footer shows `answer_model`, `embedding_provider`, `top-k`, and Phase 4 `token_usage` as a single dim line under the answer.
- Sample questions shown in the empty state instead of marketing copy.

### Library
- Replaced the seven-control filter row + density toggle + page-size selector + sort selector with: search input, status filter, "Upload PDF" CTA. No "What Happens Next" 1-2-3 explainer, no "Operational Snapshot" badge row, no "Latest Corpus Event" banner.
- Single 6-column table: Document, Status, Type, Chunks, Updated, Actions. One badge per row max.
- Upload moved into a focused modal triggered by the header button. Delete confirm dialog kept (it was the most polished part of the original).

### Evals
- New surface (didn't exist before). Two-pane: runs list on the left, run detail on the right.
- Header buttons: "Run dense" / "Run hybrid" — clicking either fires `POST /api/evals/run` with the appropriate mode and refreshes the list. This is the explicit dense-vs-hybrid comparison surface.
- Per-run aggregate header: Cases, Recall@k, MRR, Citation correctness, Abstain accuracy, Judge score (1-5).
- Per-case table: question, category, R@k, MRR, citation correctness, abstain ✓/✗, judge score. Each row inspectable.

### Queries
- New surface. Filterable feed (All / Answer / Query / Errors) of every `/api/query` and `/api/answer` request.
- Detail pane shows question, endpoint, embedding provider, answer model, latency, token usage, retrieved chunks with scores, citations, and any error.

### Files
New: [apps/web/lib/types.ts](apps/web/lib/types.ts), [apps/web/lib/api.ts](apps/web/lib/api.ts), [apps/web/components/ui/](apps/web/components/ui/) (button, badge, banner, empty-state), [apps/web/components/shell/](apps/web/components/shell/), [apps/web/components/qa/](apps/web/components/qa/), [apps/web/components/library/library-console.tsx](apps/web/components/library/library-console.tsx), [apps/web/components/evals/evals-dashboard.tsx](apps/web/components/evals/evals-dashboard.tsx), [apps/web/components/queries/queries-feed.tsx](apps/web/components/queries/queries-feed.tsx), [apps/web/app/library/page.tsx](apps/web/app/library/page.tsx), [apps/web/app/evals/page.tsx](apps/web/app/evals/page.tsx), [apps/web/app/queries/page.tsx](apps/web/app/queries/page.tsx).

Modified: [apps/web/app/layout.tsx](apps/web/app/layout.tsx), [apps/web/app/page.tsx](apps/web/app/page.tsx), [apps/web/app/globals.css](apps/web/app/globals.css), [apps/web/tailwind.config.ts](apps/web/tailwind.config.ts), [apps/web/tsconfig.json](apps/web/tsconfig.json).

Deleted: `apps/web/components/phase-one-console.tsx` (2003 lines → split across the new routes).

### How to verify
After `npm run dev` from `apps/web`:
- `/` shows a single composer + answer area with inline `[N]` citation markers; clicking a marker highlights/scrolls its evidence row in the panel beside it. Click the confidence chip to expand evidence-derived signals.
- `/library` shows a clean table with Upload PDF in the header.
- `/evals` shows runs list + detail; "Run hybrid" / "Run dense" buttons trigger eval runs.
- `/queries` shows newest-first request log with detail pane.
- Type system: Inter and Fraunces; no Trebuchet anywhere. One spacing/radius scale visible across all four routes.

### What's left for the frontend follow-up
- F3 (shipped, see below).
- F4 (shipped, see below).
- F5 (shipped, see below).
- F5b (shipped, see below).
- F6 (shipped, see below).

## Phase F3 — Eval run comparison

New route [`/evals/compare`](apps/web/app/evals/compare/page.tsx). Two run pickers default to the latest two completed runs; once both are selected, the page renders:

- Side-by-side run headers (mode, top-k, `config_hash` short).
- Aggregate diff table — Recall@k, MRR, Citation correctness, Abstain accuracy, Judge — with `Δ = B − A`. Positive deltas are emerald, negative are rose, ties are dimmed.
- Per-case table joined by `case_id` showing each metric's A / B / Δ side by side.
- A win counter (B-wins / A-wins / ties) computed against `recall_at_k`.
- A warning banner when both runs share the same `config_hash` (deltas are run-to-run noise only).

The runs list at `/evals` now has a "Compare runs →" link in the header so the surface is discoverable without changing existing flows.

This is the surface that makes the Phase 6 dense-vs-hybrid narrative *concrete*: pick the dense run, pick the hybrid run, see the actual `+0.07` recall delta with the per-case breakdown explaining where it came from.

## Phase F4 — Library metadata editing

`api.patchDocument` wired to `PATCH /documents/{id}` (Phase 5 backend). Each library row gains an "Edit" action that opens a focused modal with the seven editable fields (title, document_type, department, policy_status as a select, version_label, effective_date, review_date as native date pickers). Only changed fields are sent; blanking a field clears it back to `null` (heuristic detection takes over again on next reindex). On success the row refreshes inline.

This finally closes the "no path to fix wrong heuristics from the UI" loop that the audit's H7 / M9 entries had.

### Files
New: [apps/web/app/evals/compare/page.tsx](apps/web/app/evals/compare/page.tsx), [apps/web/components/evals/eval-compare.tsx](apps/web/components/evals/eval-compare.tsx).
Modified: [apps/web/lib/api.ts](apps/web/lib/api.ts), [apps/web/components/evals/evals-dashboard.tsx](apps/web/components/evals/evals-dashboard.tsx), [apps/web/components/library/library-console.tsx](apps/web/components/library/library-console.tsx).

## Phase F5 — Stage-level streaming + keyboard focus

### Backend
- **New endpoint** `POST /api/answer/stream` returning Server-Sent Events. Frame format is the canonical `event: <name>\ndata: <json>\n\n`.
- Events:
  - `retrieval` — fired once retrieval succeeds; payload includes `embedding_provider`, `retrieval_mode`, `top_k`, and the full retrieved-chunk list.
  - `complete` — terminal happy-path event with the full `AnswerResponse` (same shape as the non-streaming endpoint).
  - `error` — terminal failure event with a `message` string.
- Retrieval and composition are dispatched via `asyncio.to_thread` so the event loop isn't blocked on Qdrant + OpenAI calls.
- The `query_logs` row is still persisted at the end of the stream (success or failure) — observability stays consistent across the streaming and non-streaming paths.
- `AnsweringService` refactored: `retrieve(...)` and `compose(...)` are now public; `answer(...)` keeps its previous signature and just composes the two. The streaming endpoint can step through retrieval → emit event → compose, while the non-streaming endpoint and the eval runner keep using `answer(...)` as before.

### Frontend
- New `api.streamAnswer(...)` consumer in [apps/web/lib/api.ts](apps/web/lib/api.ts). Uses `fetch()` + `ReadableStream` rather than the native `EventSource` (which only supports GET) and dispatches typed events to `onRetrieval` / `onComplete` / `onError` handlers. `AbortController` cleanup on unmount or page change.
- `QaWorkspace` rewritten around an explicit four-stage state machine (`idle | retrieving | composing | done | error`). Visible UX:
  - Click *Ask* → "Retrieving evidence…" skeleton card on the left, evidence skeleton on the right.
  - `retrieval` event arrives → evidence list populates immediately with retrieval scores; answer card flips to "Generating answer…" with an animated placeholder.
  - `complete` event arrives → answer card replaces the placeholder; inline citation markers wire up to the same evidence list that's already on screen.
- ⌘K (Ctrl+K on Linux/Windows) focuses the composer textarea via a global keydown listener. Hint chip in the workspace header makes it discoverable. ⌘+Enter to submit was already there.

### Files
New: [apps/api/app/api/routes/stream.py](apps/api/app/api/routes/stream.py).
Modified: [apps/api/app/api/router.py](apps/api/app/api/router.py), [apps/api/app/services/answering.py](apps/api/app/services/answering.py), [apps/web/lib/api.ts](apps/web/lib/api.ts), [apps/web/components/qa/qa-workspace.tsx](apps/web/components/qa/qa-workspace.tsx), [apps/web/components/qa/composer.tsx](apps/web/components/qa/composer.tsx).

## Phase F5b — Token-level streaming

The answer now fills in character-by-character as the model emits it, replacing the placeholder card from F5.

### Backend
- New `app/services/answer_stream.py` with two pieces:
  - **`AnswerFieldStreamer`** — a JSON-aware state machine that pulls the top-level `"answer"` field's characters out of streaming structured-output deltas. Handles escape sequences (`\n`, `\t`, `\r`, `\b`, `\f`, `\"`, `\\`, `\/`, `\uXXXX`), whitespace around the colon and opening quote, and chunk boundaries that split the key, an escape, or a unicode point. Stops emitting once the closing quote is consumed.
  - **`stream_compose(...)`** — async generator that uses the OpenAI Responses streaming API (`AsyncOpenAI.responses.stream(text_format=AnswerDraft)`), feeds each `response.output_text.delta` into the streamer, and yields `answer_delta` events as characters become available. After the model completes, calls `stream.get_final_response()` and yields a terminal `complete` event with the full `AnswerResponse` (citations + confidence + token usage). Falls back to the synchronous `compose(...)` path if the OpenAI call fails or no key is configured — in that case the answer is yielded as a single `answer_delta` followed by `complete`, so the frontend has one rendering path.
- The streaming endpoint at [/api/answer/stream](apps/api/app/api/routes/stream.py) now consumes `stream_compose(...)` and forwards `answer_delta` events as they arrive. Logging still happens once on `complete` (or once on `error`).
- 9 new tests for `AnswerFieldStreamer` covering chunk-boundary safety, all JSON escape sequences, unicode escapes split mid-sequence, missing-field tolerance, and post-close termination.

### Frontend
- `streamAnswer` consumer gains an `onAnswerDelta` handler.
- `QaWorkspace` keeps a `partialAnswer: string` in its streaming state; each `answer_delta` appends to it. While the answer is composing, a `StreamingAnswer` component renders the live text plus a 1-pixel blinking cursor. On `complete`, the card swaps to the final `AnswerWithCitations` render with inline `[N]` markers (which the streaming text intentionally lacks — the model's citation list isn't ready until the JSON parses fully).

### How to verify
With `OPENAI_API_KEY` set, ask a question on `/`. Expected sequence: "Retrieving evidence…" skeleton → evidence list populates → live answer text starts streaming with cursor → answer card swaps to inline-citation render once the model finishes. Without an API key, the extractive fallback renders as one delta followed by `complete`, so the surface still works (just no token-by-token reveal).

### Files
New: [apps/api/app/services/answer_stream.py](apps/api/app/services/answer_stream.py), [apps/api/tests/test_answer_stream.py](apps/api/tests/test_answer_stream.py).
Modified: [apps/api/app/api/routes/stream.py](apps/api/app/api/routes/stream.py), [apps/web/lib/api.ts](apps/web/lib/api.ts), [apps/web/components/qa/qa-workspace.tsx](apps/web/components/qa/qa-workspace.tsx).

## Phase F6 — Mobile polish

Wide tables on `/library`, `/evals` (per-case detail), and `/evals/compare` (aggregate + per-case) are now wrapped in `overflow-x-auto` containers with `min-w-[N]` floors so the table layout stays readable and horizontally scrollable on narrow viewports instead of mangling. The two-pane (`lg:grid-cols-…`) layouts on `/evals`, `/evals/compare`, and `/queries` already collapse to single column below the `lg` breakpoint via Tailwind defaults; no change needed there. The home page's answer + evidence layout was already mobile-stacked.

Deeper mobile polish (card-based row layouts, abbreviated columns, hamburger nav) is deferred — the wrapped tables are good enough to keep all four routes usable on a phone in portrait, and the portfolio screenshot story is desktop-first anyway.

### Files
Modified: [apps/web/components/library/library-console.tsx](apps/web/components/library/library-console.tsx), [apps/web/components/evals/evals-dashboard.tsx](apps/web/components/evals/evals-dashboard.tsx), [apps/web/components/evals/eval-compare.tsx](apps/web/components/evals/eval-compare.tsx).
