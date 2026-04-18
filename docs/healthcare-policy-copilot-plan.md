# Healthcare Policy Copilot Implementation Plan

Last updated: 2026-04-17

## 1. Project Goal

Build a portfolio-quality RAG application that answers questions over healthcare policy and procedure documents with:

- grounded answers
- inline citations
- clickable source excerpts
- confidence signals
- evaluation results
- a polished web UI and API

This project should feel like an internal assistant a hospital operations, compliance, or care-management team could plausibly use.

## 2. What Makes This Project Strong

This project is valuable because it shows the full applied AI stack recruiters actually care about:

- document ingestion and normalization
- chunking and metadata design
- embeddings and vector search
- reranking and retrieval tuning
- answer generation with evidence grounding
- confidence and abstention behavior
- evaluation harnesses and failure analysis
- product UX, API design, and deployment

The goal is not just "chat with PDFs." The goal is "build a trustworthy retrieval product with measurable quality."

## 3. Recommended Scope

### MVP

The MVP should support:

- uploading healthcare policy PDFs
- parsing and indexing them
- asking natural-language questions
- returning answers with citations
- showing the exact supporting excerpts
- showing low/medium/high confidence
- logging queries, retrieved chunks, and feedback

### V1.5

After the MVP works end to end, add:

- metadata filters by policy type, department, and effective date
- version-aware retrieval so retired policies do not outrank current ones
- hybrid retrieval
- reranking
- an evaluation dashboard or report

### Explicit Non-Goals For The First Version

Do not start with these:

- agentic multi-step tool use
- patient-specific medical advice
- production HIPAA workflows
- voice interfaces
- complex RBAC or SSO
- fine-tuning

Those will slow down the flagship project without improving the portfolio signal enough.

## 4. Product Definition

### Primary User

An internal healthcare operations user who needs quick, evidence-backed answers about procedures, policies, or admin rules.

### Example Questions

- "What is the prior authorization escalation process for urgent cases?"
- "When does a denied claim need to be refiled?"
- "Which team owns discharge planning follow-up?"
- "What changed in the 2026 infection-control policy?"
- "Does this policy mention telehealth documentation requirements?"

### Key UX Promise

Every substantive claim should be traceable back to a policy chunk the user can inspect.

## 5. Recommended Stack

This is the stack I recommend for the project.

- Frontend: Next.js + TypeScript + Tailwind
- Backend: FastAPI + Python 3.12
- Relational store: Postgres
- Vector store: Qdrant
- LLMs and embeddings: OpenAI API
- Background jobs: start simple with FastAPI background tasks, move to Redis + worker only if ingest volume justifies it
- Object/file storage: local `data/` for development, S3-compatible storage later if needed
- Observability: structured logs first, Langfuse or OpenTelemetry only if time remains
- Deployment: Vercel for web, Fly.io or Render for API, Qdrant Cloud, Neon/Supabase Postgres

### Why This Stack

- `FastAPI` is fast to build, test, and demo.
- `Next.js` gives a portfolio-friendly UI with shareable screenshots.
- `Postgres + Qdrant` is the cleanest separation between source-of-truth metadata and retrieval infrastructure.
- `OpenAI` gives current best-in-class general-purpose models, embeddings, eval tooling, and citation guidance.

## 6. Recommended Model Strategy

These choices are based on current OpenAI docs and pricing pages reviewed on 2026-04-17.

- Default answer model: `gpt-5.4-mini`
- Higher-precision answer/eval model: `gpt-5.4`
- Embeddings default: `text-embedding-3-large` with `dimensions=1024`
- Embeddings budget fallback: `text-embedding-3-small`

### Why

- OpenAI currently recommends starting with `gpt-5.4` for complex reasoning and `gpt-5.4-mini` for lower-latency, lower-cost workloads.
- `gpt-5.4-mini` is the right default for the interactive app.
- `gpt-5.4` is useful for harder benchmark questions and judge-style evaluation passes.
- `text-embedding-3-large` is the strongest embedding option and supports dimension shortening, so `1024` dimensions is a strong quality/storage tradeoff for this project.

This `1024` choice is a design recommendation, not an OpenAI default. The docs explicitly support shortening dimensions; the exact dimension is our implementation choice.

## 7. Core System Architecture

```text
PDF Upload
  -> parse + normalize
  -> extract metadata
  -> chunk by section
  -> generate embeddings
  -> store canonical docs/chunks in Postgres
  -> store vectors + payload metadata in Qdrant

User Query
  -> normalize query
  -> optional metadata filter
  -> retrieve candidate chunks
  -> rerank candidates
  -> send top evidence to LLM
  -> structured answer + citations + confidence
  -> log query, retrieval, cost, latency, feedback
```

## 8. Data And Document Strategy

### Corpus Strategy

Use one of these:

- public healthcare policy or procedure documents
- public payer/provider administrative manuals
- synthetic hospital SOPs modeled after real formats
- a mixed demo corpus with policy memos, procedures, and department guidelines

### Important Constraint

Do not use real PHI or patient records in this project.

This should be a policy assistant, not a medical diagnosis or patient chart assistant.

### Recommended Starter Corpus

Aim for:

- 20-50 documents
- 150-500 total chunks after processing
- a mix of short and long policies
- at least a few versioned or superseded documents

That is large enough to make retrieval meaningful without turning the project into a data-engineering marathon.

## 9. Parsing And Normalization Plan

### Parsing Pipeline

1. Accept PDF upload.
2. Extract raw text with page boundaries.
3. Detect headings, numbered sections, tables, lists, and appendices.
4. Normalize whitespace, bullets, headers, and repeated footers.
5. Extract metadata.
6. Store the original file and normalized text representation.

### Metadata To Extract

- `document_id`
- `title`
- `document_type`
- `department`
- `effective_date`
- `review_date`
- `status` such as `active`, `draft`, `retired`
- `version`
- `supersedes_document_id`
- `source_filename`
- `page_count`
- `checksum`

### Practical Parsing Notes

- Start with text-based PDFs only.
- If image-only PDFs appear, add OCR as a later enhancement.
- Preserve page numbers and section paths because they matter for citations and trust.

## 10. Chunking Strategy

Chunking quality will decide whether this project feels sharp or mediocre.

### Recommended Chunking Approach

Use hierarchical chunking:

1. Split by top-level sections and subsections first.
2. Then split long sections into token-sized chunks.
3. Preserve section titles in each chunk.
4. Preserve page start/end and nearby context.

### Recommended Starting Heuristics

- target chunk size: 350-600 tokens
- overlap: 60-100 tokens
- smaller chunks for dense tables, definitions, and lists
- never merge unrelated headings into a single chunk

These are implementation recommendations, not values pulled directly from a vendor default.

### What To Store Per Chunk

- `chunk_id`
- `document_id`
- `chunk_index`
- `section_path`
- `page_start`
- `page_end`
- `token_count`
- `text`
- `normalized_text`
- `citability_label`
- `version_metadata`

### Why This Matters

The best citation UX comes from stable, inspectable block-level chunks. OpenAI’s citation guidance explicitly recommends clear citable units and notes that block-level citations are the best default for most systems.

## 11. Retrieval Plan

Build retrieval in stages. Do not jump straight to the fanciest pipeline.

### Stage 1: Dense Retrieval

- embed all chunks
- embed user query
- retrieve top 20 candidates from Qdrant
- filter by metadata when the query or UI constrains scope

This gets the app working quickly.

### Stage 2: Hybrid Retrieval

Add keyword-aware retrieval so policy titles, acronyms, codes, and exact terms are not missed.

Recommended approach:

- dense vector search for semantic recall
- sparse/BM25 search for keyword recall
- fuse results with Qdrant hybrid queries

Qdrant’s hybrid query docs explicitly support combining dense and sparse search via `prefetch` and fusion.

### Stage 3: Reranking

After hybrid retrieval, rerank the top 20 results and pass only the top 5-8 to generation.

Good options:

- ColBERT-style late interaction reranking in Qdrant
- external reranker model if you want a simpler implementation later

The pragmatic call:

- MVP: dense retrieval only
- V1.5: hybrid retrieval
- V2: reranking if evals show retrieval misses or ranking noise

### Metadata Filtering

Use Qdrant payload filters and Postgres metadata for:

- active vs retired policies
- department scope
- policy type
- effective date windows
- version selection

This is especially important in healthcare because outdated policies are a trust killer.

### Diversity Control

Use MMR or a similar diversity pass when the top results are near-duplicate chunks from the same section.

## 12. Answer Generation Plan

### Generation Flow

1. Retrieve and rerank evidence.
2. Build a structured context packet with stable source IDs.
3. Ask the model to answer only from that context.
4. Require citations for every factual claim.
5. Return structured output.

### Prompt Rules

The answer prompt should instruct the model to:

- answer only from retrieved policy evidence
- cite each important claim
- say when evidence is insufficient
- avoid pretending to know policy details not present in the retrieved material
- distinguish between current and retired policies when relevant

### Output Shape

Return JSON from the backend such as:

```json
{
  "answer": "text",
  "citations": [
    {
      "chunk_id": "chunk_42",
      "document_title": "Utilization Review Policy",
      "section_path": "4.2 Urgent Prior Authorization",
      "page_start": 7,
      "page_end": 8,
      "quote_preview": "..."
    }
  ],
  "confidence": "medium",
  "confidence_reasons": [
    "Multiple active-policy citations support the answer",
    "The answer depends on one ambiguous clause"
  ],
  "abstained": false
}
```

### Structured Output Advantage

This keeps the UI stable and makes evaluation much easier than parsing free-form text after the fact.

## 13. Citation UX Plan

The citation experience is one of the strongest portfolio differentiators.

### UI Behavior

- show inline citation badges like `[1] [2]`
- clicking a citation opens a right-side evidence panel
- evidence panel shows document title, section, page range, and the quoted excerpt
- highlight the exact span used by the answer when possible

### Citation Granularity

Use block-level chunk citations for the main product.

If you have time later, add line-range citations within the chunk renderer.

### Why

OpenAI’s citation formatting guide emphasizes:

- stable source IDs
- clear material representation
- an explicit citation format
- parsing citations for downstream UI rendering

That maps directly to this product.

## 14. Confidence Signal Design

Do not use raw model self-confidence as the primary signal.

Confidence should be derived from evidence quality and answer support.

### Recommended Confidence Inputs

- top retrieval score and score margin
- number of unique supporting chunks
- number of unique supporting documents
- whether all citations are from active documents
- answer-support grader result
- contradiction or insufficiency check
- whether the answer required cross-document synthesis

### Suggested Confidence Buckets

`High`

- at least 2 strong supporting citations
- no contradiction detected
- active/current policy support
- support grader passes

`Medium`

- answer appears grounded but evidence is thinner, more ambiguous, or concentrated in one chunk

`Low`

- weak retrieval
- conflicting chunks
- only partial support
- outdated or draft-only support

### Important Rule

If evidence is weak, abstain instead of bluffing.

Example UX:

- "I found related policy text, but not enough support to answer confidently."

That behavior is a feature, not a weakness.

## 15. Version-Aware Policy Handling

This is a very strong domain-specific differentiator.

### Requirements

- mark documents as active/draft/retired
- track effective dates
- track superseded relationships
- prefer current policies in retrieval and ranking
- show version metadata in the citation panel

### UI Behavior

If a retired policy is cited, label it clearly.

If the answer depends on a policy revision, say so explicitly.

## 16. Storage Design

### Postgres Tables

Recommended tables:

- `documents`
- `document_versions`
- `chunks`
- `queries`
- `retrieval_events`
- `answers`
- `feedback`
- `eval_runs`
- `eval_cases`

### Qdrant Payload Schema

Store payload fields such as:

- `document_id`
- `chunk_id`
- `title`
- `document_type`
- `department`
- `status`
- `effective_date`
- `version`
- `section_path`
- `page_start`
- `page_end`

### Separation Of Concerns

- Postgres is the canonical metadata and analytics store.
- Qdrant is the retrieval engine.

Do not try to turn the vector DB into the whole application database.

## 17. Backend API Plan

Recommended endpoints:

- `POST /api/documents/upload`
- `POST /api/documents/{id}/index`
- `GET /api/documents`
- `GET /api/documents/{id}`
- `POST /api/query`
- `GET /api/query/{id}`
- `POST /api/feedback`
- `POST /api/evals/run`
- `GET /api/evals`

### `/api/query` Request

```json
{
  "question": "What is the urgent prior auth escalation path?",
  "filters": {
    "department": "utilization_management",
    "status": "active"
  }
}
```

### `/api/query` Response

Return:

- final answer
- citations
- retrieved chunk summaries
- confidence
- timing
- token usage

## 18. Frontend Plan

### Main Screens

1. Chat/Search screen
2. Evidence drawer or side panel
3. Document library/admin upload page
4. Eval results page or report page

### Main UI Elements

- search box
- answer card
- confidence badge
- citations list
- evidence panel
- filters bar
- document badges such as `Active`, `Retired`, `Draft`

### Good UX Details

- stream the answer
- show "retrieving sources" while search runs
- keep source cards visible under the answer
- let users thumbs-up/down the response
- let users inspect the top retrieved chunks even if the final answer abstains

That last point is important. It makes the system feel transparent instead of magical.

## 19. Evaluation Plan

This section is mandatory if you want the project to stand out.

### Build A Real Eval Set

Create a labeled QA set with at least:

- 30 questions for the first working benchmark
- 75-150 questions for the polished version

### Question Categories

Include:

- direct lookup
- multi-hop policy synthesis
- version-sensitive questions
- ambiguous questions
- no-answer / abstain questions
- near-miss wording
- acronym-heavy questions
- policy comparison questions

### Retrieval Metrics

Track:

- Recall@k
- Precision@k
- MRR
- nDCG

Qdrant’s retrieval quality docs explicitly call out metrics like Precision@k and recommend measuring retrieval quality directly rather than only judging final answers.

### Answer Quality Metrics

Track:

- groundedness / faithfulness
- citation correctness
- completeness
- abstention accuracy
- latency
- cost per question

### Evaluation Process

1. Build test set in JSONL or CSV.
2. Run the pipeline against the test set.
3. Save retrieved chunks, answers, citations, latency, and token usage.
4. Grade outputs with a mix of:
   - exact checks where possible
   - model graders for groundedness and completeness
   - manual review on failures
5. Compare runs across chunking, embedding, and retrieval changes.

### OpenAI Evals Usage

OpenAI’s eval docs support defining test criteria, uploading JSONL data, and running evals against model outputs. Use that for answer-level grading or prompt iteration.

### Minimum Evaluation Dashboard

Show:

- overall scorecard
- retrieval hit rate
- groundedness score
- abstain precision
- latency distribution
- top failure examples

## 20. Recommended Experiments

These experiments make the project look like serious engineering work.

### Experiment 1: Chunk Size Ablation

Compare:

- 250-350 token chunks
- 350-600 token chunks
- 600-900 token chunks

Measure retrieval hit rate and citation usefulness.

### Experiment 2: Embedding Comparison

Compare:

- `text-embedding-3-large` at 1024 dimensions
- `text-embedding-3-small`

Measure retrieval quality, storage, and cost.

### Experiment 3: Dense vs Hybrid

Compare:

- dense only
- dense + sparse fusion

Measure acronym and exact-term performance.

### Experiment 4: With vs Without Reranking

Compare:

- top-k direct generation
- top-k plus reranker

Measure groundedness and answer quality.

### Experiment 5: Confidence Calibration

Measure whether low-confidence answers actually fail more often than high-confidence ones.

If confidence does not correlate with quality, the system needs redesign.

## 21. Logging And Observability Plan

Log every query with:

- normalized query text
- filters used
- retrieved chunk IDs
- retrieval scores
- final citations
- confidence score and reasons
- model name
- token usage
- latency
- user feedback

This gives you:

- debugging leverage
- evaluation data
- portfolio screenshots
- a realistic story about operating AI systems

## 22. Testing Plan

### Unit Tests

Write tests for:

- chunking logic
- metadata extraction
- citation parsing
- confidence bucketing
- filter construction

### Integration Tests

Write tests for:

- PDF upload to indexed chunks
- query to retrieved sources
- query to answer JSON shape
- abstention on unsupported questions

### Golden Tests

Create 10-20 must-pass benchmark questions.

Run them before major retrieval or prompt changes.

## 23. Safety And Trust Requirements

Even as a portfolio project, this should have sane guardrails.

### Product Rules

- do not present the system as medical advice
- answer only from uploaded policies
- abstain when evidence is weak
- label outdated policies clearly
- avoid hidden chain-of-thought displays

### UI Copy

Use a short disclaimer such as:

"This assistant summarizes uploaded policy documents. It is not a substitute for clinical judgment or official policy review."

## 24. Suggested Repository Structure

```text
Healthcare-Policy-Copilot/
  apps/
    api/
      app/
      tests/
    web/
      app/
      components/
  packages/
    shared/
    evals/
  data/
    raw/
    processed/
    evals/
  docs/
    healthcare-policy-copilot-plan.md
    architecture-diagram.png
    screenshots/
  infra/
    docker/
  scripts/
  docker-compose.yml
  README.md
```

## 25. 4-Week Delivery Plan

### Week 1: Foundation

Ship:

- repo scaffolding
- FastAPI backend
- Next.js frontend shell
- Postgres + Qdrant local setup
- PDF upload flow
- parsing + metadata extraction
- chunking pipeline
- dense indexing

Definition of done:

- documents upload successfully
- chunks and metadata are inspectable
- query endpoint returns top retrieved chunks

### Week 2: Answering Experience

Ship:

- query pipeline
- answer generation
- inline citations
- evidence panel
- confidence v1
- query logging

Definition of done:

- user can ask questions and inspect evidence
- unsupported questions abstain sometimes instead of hallucinating

### Week 3: Retrieval Quality And Evals

Ship:

- eval dataset
- offline eval runner
- retrieval metrics
- answer graders
- dense vs hybrid comparison
- better policy version handling

Definition of done:

- you can show a before/after table for retrieval or answer quality

### Week 4: Polish And Portfolio Assets

Ship:

- reranking if it clearly improves quality
- admin library polish
- screenshots
- architecture diagram
- evaluation table
- failure case write-up
- deployment
- polished README and portfolio summary

Definition of done:

- the project is demoable end to end
- the repo and screenshots tell a coherent story

## 26. If You Only Have 2 Weeks

Cut scope aggressively:

- use dense retrieval only
- skip hybrid until after the demo works
- skip OCR
- keep the eval set to 30-40 questions
- use one clean UI flow
- prioritize citations, abstention, and evaluation over extra features

If forced to choose, always keep:

- citations
- confidence states
- eval dataset
- failure analysis

Those are what make the project look serious.

## 27. Portfolio Deliverables To Capture

Prepare these for your portfolio page:

- homepage screenshot with answer + citations
- evidence panel screenshot
- retrieval pipeline diagram
- architecture diagram
- evaluation results table
- one failure case example
- one retrieval improvement example
- short section explaining how confidence is computed

### Strong Narrative

Frame the project like this:

"I built a healthcare policy assistant that retrieves, reranks, cites, and evaluates evidence-backed answers over operational policy documents. I focused on trust features: grounded responses, version-aware retrieval, abstention behavior, and measurable evals."

## 28. Stretch Goals

Only do these after the core project is already polished.

- OCR pipeline for scanned PDFs
- document diff view for policy revisions
- user feedback learning loop
- query analytics dashboard
- role-aware retrieval filters
- multilingual support
- synthetic policy generator for expanded eval coverage

## 29. Biggest Risks And How To Control Them

### Risk 1: Poor PDF Parsing

Mitigation:

- start with clean text PDFs
- inspect parsed output early
- build a chunk preview page

### Risk 2: Weak Retrieval

Mitigation:

- evaluate retrieval separately from generation
- add metadata filters
- add hybrid retrieval before touching prompts too much

### Risk 3: Hallucinated Answers

Mitigation:

- require citations
- use abstention rules
- add answer-support grading

### Risk 4: Outdated Policy Ranking

Mitigation:

- store version metadata
- boost active policies
- visibly label retired ones

### Risk 5: Scope Creep

Mitigation:

- lock MVP first
- treat reranking and dashboards as phase-two items

## 30. Recommended Build Order

This is the exact order I would follow:

1. scaffold repo and infra
2. upload and parse PDFs
3. define metadata schema
4. build chunker and inspect chunk quality
5. generate embeddings and index in Qdrant
6. expose retrieval endpoint
7. add answer generation with structured output
8. add citations and evidence panel
9. add confidence and abstention
10. create eval dataset
11. measure retrieval and answer quality
12. add hybrid retrieval
13. add reranking only if metrics justify it
14. polish deployment and portfolio assets

## 31. Final Recommendation

The best version of this project is not the most complicated version.

The best version is:

- clearly scoped
- visibly trustworthy
- measurable
- strong on citations
- strong on failure handling
- strong on evaluation

If the project ends with a clean UI, reliable citations, version-aware retrieval, and a real eval table, it will already be an excellent flagship portfolio piece.

## 32. Sources Reviewed

Official sources reviewed on 2026-04-17:

- OpenAI models guide: https://developers.openai.com/api/docs/models
- OpenAI embeddings guide: https://developers.openai.com/api/docs/guides/embeddings
- OpenAI `text-embedding-3-large` model page: https://developers.openai.com/api/docs/models/text-embedding-3-large
- OpenAI `text-embedding-3-small` model page: https://developers.openai.com/api/docs/models/text-embedding-3-small
- OpenAI citation formatting guide: https://developers.openai.com/api/docs/guides/citation-formatting
- OpenAI working with evals guide: https://developers.openai.com/api/docs/guides/evals
- OpenAI production best practices: https://developers.openai.com/api/docs/guides/production-best-practices
- Qdrant filtering docs: https://qdrant.tech/documentation/concepts/filtering/
- Qdrant hybrid queries docs: https://qdrant.tech/documentation/concepts/hybrid-queries/
- Qdrant hybrid search with reranking tutorial: https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search/
- Qdrant retrieval quality evaluation tutorial: https://qdrant.tech/documentation/beginner-tutorials/retrieval-quality/
- Qdrant search relevance docs: https://qdrant.tech/documentation/search/search-relevance/

### What Is Inferred Vs Directly Documented

The following are my design recommendations inferred from the sources and the project constraints, not vendor-mandated defaults:

- the exact 2-4 week roadmap
- the recommended repo structure
- the `gpt-5.4-mini` default plus `gpt-5.4` fallback split for this product
- the choice to use `text-embedding-3-large` at `1024` dimensions
- the proposed chunk sizes and overlaps
- the specific confidence bucketing strategy
- the sequence of dense -> hybrid -> rerank rollout
