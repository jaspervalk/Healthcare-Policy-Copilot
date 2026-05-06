# Project Architecture

A reference map for navigating this repo. Skim by section, jump by file path.

## Top-level layout

```
apps/
  api/                    FastAPI backend (Python 3.12)
  web/                    Next.js 15 frontend (React 19, Tailwind 3)
data/
  raw/                    Uploaded source PDFs
  processed/              Per-document JSON artifacts
  qdrant/                 Embedded local Qdrant storage
  app.db                  SQLite (default DB)
docs/
  healthcare-policy-copilot-plan.md
docker-compose.yml        Optional Postgres + Qdrant services
.env.example              Environment variable template
README.md
PROJECT_ARCH.md           This file
```

## Backend (apps/api)

### Entry points

| File | Purpose |
|---|---|
| `apps/api/app/main.py` | FastAPI app, CORS, lifespan: creates dirs, runs `init_db`, warms BM25 index |
| `apps/api/app/db.py` | Engine, `SessionLocal`, `Base`, `get_db`, `init_db` (idempotent ADD COLUMN migration on startup) |
| `apps/api/app/core/config.py` | `Settings` (env-driven, pydantic-settings). `ROOT_DIR = parents[4]` of this file |
| `apps/api/app/models.py` | SQLAlchemy 2.x models: `Document`, `Chunk`, `QueryLog`, `IndexCollection`, `EvalRun`, `EvalCase` |
| `apps/api/app/schemas.py` | Pydantic request/response schemas including `AnswerResponse`, `QueryRequest`, `EvalRunRequest` |

### HTTP layer (`apps/api/app/api/`)

| File | Purpose |
|---|---|
| `api/router.py` | Mounts route modules under `/api` |
| `api/auth.py` | Optional admin token gate for destructive routes |
| `api/errors.py` | Centralized exception → HTTP status mapping |
| `api/routes/health.py` | `GET /api/health` |
| `api/routes/documents.py` | Upload, reindex, PATCH metadata, delete, list, get |
| `api/routes/query.py` | `POST /api/query` (retrieval only), `POST /api/answer` (non-streaming) |
| `api/routes/stream.py` | `POST /api/answer/stream` — SSE |
| `api/routes/queries.py` | Query log feed: `GET /api/queries`, `GET /api/queries/{id}` |
| `api/routes/evals.py` | `POST /api/evals/run`, `GET /api/evals`, `GET /api/evals/{id}` |

### Services (`apps/api/app/services/`)

| File | Purpose |
|---|---|
| `services/upload_safety.py` | Multipart size cap + `%PDF-` magic-byte check before disk write |
| `services/storage.py` | SHA-256 checksum, sanitised path resolution, raw/processed file IO |
| `services/pdf_parser.py` | pypdf wrapper, header/footer stripping, title inference |
| `services/chunking.py` | Heading-aware blocks, sliding word windows (425 / 75 overlap), per-chunk page span |
| `services/documents.py` | Ingestion pipeline: parse → metadata heuristics → chunk → embed → upsert. Atomic SQL+Qdrant write with rollback. Heuristic detectors: `_detect_document_type`, `_detect_department`, `_detect_policy_status`, `_detect_version`, `_extract_date` |
| `services/embeddings.py` | OpenAI `text-embedding-3-large` (1024 dims) + `LocalHashingEmbedder` fallback (256 dims). Strict — no silent provider switching |
| `services/index_stamp.py` | Validates `(provider, model, dim)` against `IndexCollection` row before any write |
| `services/qdrant_index.py` | Collection management, payload indexes, `replace_document_chunks`, dense search |
| `services/hybrid_index.py` | In-memory BM25 over chunk text, RRF fusion (`rrf_fuse`), refresh-from-SQL helper |
| `services/retrieval.py` | `RetrievalService` — dense or hybrid mode, filter-aware sparse drop |
| `services/answering.py` | `AnsweringService.compose`, structured-output schema (`AnswerDraft`), confidence calibration (`evidence_confidence`, `combine_confidence`), inline-citation safety net (`ensure_inline_citation_markers`), suggestion sanitiser (`sanitize_suggested_questions`) |
| `services/answer_stream.py` | `AnswerFieldStreamer` JSON state machine, `stream_compose` async iterator |
| `services/query_logs.py` | `log_query`, `log_answer`, `log_failure`. Own SQL session so logging can't poison request transaction |

### Eval harness (`apps/api/app/eval/`)

| File | Purpose |
|---|---|
| `eval/dataset.py` | JSONL loader with regex-whitelisted dataset names + path-traversal defense |
| `eval/datasets/medicare_starter.jsonl` | 31 cases, 8 categories |
| `eval/datasets/README.md` | Dataset format spec |
| `eval/metrics.py` | Recall@k, MRR, citation correctness, abstention correctness |
| `eval/judge.py` | LLM-as-judge groundedness scorer (1–5) |
| `eval/runner.py` | Orchestration: per-case run, persist `EvalRun` + `EvalCase` rows, compute `config_hash` |

### Tests (`apps/api/tests/`)

134 cases. Important ones:

| File | Covers |
|---|---|
| `tests/test_chunking.py` | Window sizing, overlap, page-span, heading detection |
| `tests/test_documents.py` | Type/department/status/version heuristics, EN+NL keywords |
| `tests/test_documents_api.py` | Upload, PATCH whitelist, delete |
| `tests/test_indexing.py` | Atomic ingest rollback across SQL + Qdrant |
| `tests/test_embeddings.py` | Strict provider policy, hash fallback determinism |
| `tests/test_index_stamp.py` | Provider/model/dim mismatch rejection |
| `tests/test_hybrid_index.py` | BM25 ranking, RRF fusion |
| `tests/test_retrieval.py` | Dense, hybrid, filter-aware sparse drop |
| `tests/test_answering.py` | Confidence buckets, abstention, no-fabricated-citations invariant |
| `tests/test_answer_stream.py` | SSE shape, JSON state machine |
| `tests/test_inline_citations.py` | `[N]` and `[uuid]` parsing, safety net |
| `tests/test_query_logs.py` | Persistence, source tracking (`manual` vs `suggestion`) |
| `tests/test_eval_runner.py` | Config hash determinism |
| `tests/test_eval_dataset.py` | Path-traversal hardening |
| `tests/test_routes.py` | End-to-end API surface |
| `tests/test_errors.py` | Exception → HTTP mapping |
| `tests/test_auth.py` | Admin token gate |
| `tests/test_document_deletion.py` | Cascade + Qdrant cleanup |

## Frontend (apps/web)

### Routes (App Router)

| Path | File | Component |
|---|---|---|
| `/` | `apps/web/app/page.tsx` | `QaWorkspace` |
| `/library` | `apps/web/app/library/page.tsx` | `LibraryConsole` |
| `/evals` | `apps/web/app/evals/page.tsx` | `EvalsDashboard` |
| `/evals/compare` | `apps/web/app/evals/compare/page.tsx` | `EvalCompare` |
| `/queries` | `apps/web/app/queries/page.tsx` | `QueriesFeed` |
| (layout) | `apps/web/app/layout.tsx` | App shell, fonts |

### Components (`apps/web/components/`)

| Folder | What lives there |
|---|---|
| `components/qa/` | Q&A page: `qa-workspace.tsx` (state machine), `composer.tsx`, `answer-with-citations.tsx`, `citation-chip.tsx`, `evidence-panel.tsx`, `confidence-chip.tsx`, `abstain-notice.tsx` |
| `components/library/` | `library-console.tsx` — corpus table, upload modal, edit metadata modal, delete confirm |
| `components/evals/` | `evals-dashboard.tsx` (run list + trigger), `eval-compare.tsx` (diff two runs by `case_id`) |
| `components/queries/` | `queries-feed.tsx` — paginated query log feed with detail pane |
| `components/shell/` | `app-shell.tsx`, `nav.tsx` — global layout |
| `components/ui/` | Primitives: `button.tsx`, `badge.tsx`, `banner.tsx`, `empty-state.tsx` |

### Lib (`apps/web/lib/`)

| File | Purpose |
|---|---|
| `lib/api.ts` | All HTTP client functions, including SSE consumer (`streamAnswer`) |
| `lib/types.ts` | Shared TypeScript types mirroring backend Pydantic schemas |

### Styling

- `apps/web/tailwind.config.ts` — token system: `ink` (text/borders), `primary` (action), `accent` (status/danger), `surface`
- `apps/web/app/globals.css` — Tailwind layers + base resets

## "Where is X?" quick lookup

| If you're looking for... | Start at |
|---|---|
| How a question becomes an answer | `services/answering.py:compose` → `services/retrieval.py:search` → `services/qdrant_index.py:search` + `services/hybrid_index.py:search` |
| Streaming frame parsing | `services/answer_stream.py:AnswerFieldStreamer` |
| How citations are validated | `services/answering.py:_citation_records` |
| Why confidence is what it is | `services/answering.py:evidence_confidence` + `_bucket_from_inputs` |
| Atomic ingest pipeline | `services/documents.py:index_document` |
| Document type / status detection | `services/documents.py:_detect_document_type`, `_detect_policy_status` (EN + NL keywords) |
| Hybrid retrieval / RRF math | `services/hybrid_index.py:rrf_fuse` |
| BM25 build & query | `services/hybrid_index.py:HybridIndex` |
| Dataset path-traversal hardening | `eval/dataset.py:_resolve_path` |
| Per-run reproducibility hash | `eval/runner.py` (search for `config_hash`) |
| Query logging | `services/query_logs.py` |
| Suggestion-source tracking | `models.py:QueryLog.source`, `services/query_logs.py:log_answer(source=...)` |
| SSE event shape on the wire | `api/routes/stream.py:_format_event` |
| Frontend SSE consumer | `lib/api.ts:streamAnswer` |
| Citation chip rendering | `components/qa/citation-chip.tsx` |
| Quote highlighting in evidence | `components/qa/evidence-panel.tsx:renderHighlighted` |
| Abstention UI | `components/qa/abstain-notice.tsx` |
| Confidence chip + reasons popover | `components/qa/confidence-chip.tsx` |

## Data flow (one-liners)

**Ingest**: PDF upload → magic-byte check → SHA-256 → SQL insert → parse → heuristics → chunk → embed (batched) → stamp validation → Qdrant upsert → SQL commit → BM25 refresh → processed JSON artifact.

**Retrieve (dense)**: embed query → Qdrant search with payload filters → top-k.

**Retrieve (hybrid)**: dense top-30 + BM25 top-30 → drop sparse-only that fail dense filters → RRF fuse → resolve missing payloads via `Qdrant.retrieve(ids=...)` → top-k.

**Answer (non-streaming)**: retrieve → structured-output call → map citations to chunks → drop unrecognised → compute evidence confidence → combine with model confidence (min) → return `AnswerResponse`.

**Answer (streaming)**: retrieve → emit `retrieval` event → start streaming structured output → JSON state machine pulls answer-field bytes → emit `answer_delta` events → on done, parse final → emit `complete` event.

**Eval run**: load dataset → for each case: retrieve → answer → compute metrics → optionally judge → persist `EvalCase` row → aggregate → persist `EvalRun`.

## Environment variables

See `.env.example`. Notable:

- `OPENAI_API_KEY` — enables real embeddings + answer model. Absent: local-hash embedder + extractive fallback.
- `OPENAI_ANSWER_MODEL` — default `gpt-4.1-mini`.
- `OPENAI_EMBEDDING_MODEL` — default `text-embedding-3-large`.
- `QDRANT_URL` — empty string = embedded local mode in `data/qdrant/`. Set for hosted Qdrant.
- `DATABASE_URL` — defaults to SQLite at `data/app.db`. Set for Postgres.
- `ADMIN_TOKEN` — when set, gates `PATCH /api/documents/{id}` and `DELETE /api/documents/{id}`.

## Run locally

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
uvicorn app.main:app --reload --app-dir apps/api    # http://localhost:8000

# Frontend (separate terminal)
cd apps/web && npm install && npm run dev            # http://localhost:3000

# Tests
cd apps/api && pytest                                # 134 cases
cd apps/web && npx tsc --noEmit                      # type-check only
```

## API surface

| Method | Path | Handler |
|---|---|---|
| GET | `/api/health` | `routes/health.py` |
| GET | `/api/documents` | `routes/documents.py` |
| GET | `/api/documents/{id}` | `routes/documents.py` |
| POST | `/api/documents/upload` | `routes/documents.py` |
| POST | `/api/documents/{id}/index` | `routes/documents.py` |
| PATCH | `/api/documents/{id}` | `routes/documents.py` (admin-gated when configured) |
| DELETE | `/api/documents/{id}` | `routes/documents.py` (admin-gated when configured) |
| POST | `/api/query` | `routes/query.py` |
| POST | `/api/answer` | `routes/query.py` |
| POST | `/api/answer/stream` | `routes/stream.py` (SSE) |
| GET | `/api/queries` | `routes/queries.py` |
| GET | `/api/queries/{id}` | `routes/queries.py` |
| POST | `/api/evals/run` | `routes/evals.py` |
| GET | `/api/evals` | `routes/evals.py` |
| GET | `/api/evals/{id}` | `routes/evals.py` |
