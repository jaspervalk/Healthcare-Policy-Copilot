# Healthcare Policy Copilot

Phase 1 foundation for a healthcare-policy retrieval system with:

- FastAPI backend
- Next.js frontend shell
- PDF upload and parsing
- chunking and metadata extraction
- dense embeddings
- Qdrant indexing
- retrieval endpoint that returns top supporting chunks

## Repository Layout

```text
apps/
  api/   FastAPI ingestion and retrieval service
  web/   Next.js frontend shell and operator console
data/
  raw/        uploaded source PDFs
  processed/  parsed document artifacts
  qdrant/     local embedded Qdrant storage
docs/
  healthcare-policy-copilot-plan.md
```

## Backend Setup

1. Create a virtual environment.
2. Install the API dependencies.
3. Run the FastAPI app from the repository root.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
uvicorn app.main:app --reload --app-dir apps/api
```

The API defaults to:

- SQLite for metadata storage
- embedded local Qdrant storage in `data/qdrant/`
- OpenAI embeddings when `OPENAI_API_KEY` is set
- a deterministic local hashing embedder when the API key is absent

That fallback keeps Phase 1 runnable without external services while preserving the production OpenAI path.

## Frontend Setup

```bash
cd apps/web
npm install
npm run dev
```

The frontend expects the API at `http://localhost:8000` by default. Override it with `NEXT_PUBLIC_API_BASE_URL`.

## Optional Docker Services

If you want a more production-like local stack later, this repo includes `docker-compose.yml` for:

- Postgres
- Qdrant

Run them with:

```bash
docker compose up -d postgres qdrant
```

Then update `.env`:

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/policy_copilot
QDRANT_URL=http://localhost:6333
```

## Current Phase 1 Endpoints

- `GET /api/health`
- `POST /api/documents/upload`
- `GET /api/documents`
- `GET /api/documents/{document_id}`
- `POST /api/documents/{document_id}/index`
- `POST /api/query`

## Notes

- The upload/index flow is synchronous in Phase 1 for simplicity.
- PDF parsing starts with text-based PDFs. OCR is intentionally deferred.
- Retrieval supports metadata filters for `department`, `document_type`, and `policy_status`.

