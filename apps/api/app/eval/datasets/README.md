# Eval datasets

JSONL files. One case per line. Comment lines start with `#`. Fields:

- `id` (required) — stable case identifier, used in run output.
- `question` (required) — the natural-language question.
- `category` — one of `direct_lookup`, `multi_hop`, `version_sensitive`, `ambiguous`, `abstention`, `near_miss_wording`, `acronym_heavy`, `comparison`.
- `expected_documents` — list of `source_filename` values that should appear in retrieved chunks. Use `[]` for abstention cases.
- `should_abstain` — `true` if the system should refuse. Retrieval/citation metrics are not computed for abstention cases; only `abstain_correct` is.
- `notes` — free text, surfaced in the case row, ignored by the runner.

## medicare_starter.jsonl

30 cases targeting the Medicare Benefit Policy Manual chapters 1–3 and the Medicare General Information / Eligibility manual chapter 1.

**Ground truth is best-effort.** Expected-document mappings were inferred from chapter titles, not from reading the PDFs end-to-end. Treat the first run's recall@k numbers as a debugging tool: if a case scores 0 but the retrieved chunk looks correct, fix the `expected_documents` list. The harness is the deliverable; the dataset is meant to iterate.

## Adding cases

Append JSONL lines. To prevent regressions, prefer stable `id`s — runs are joined on `case_id` for ablation diffs.
