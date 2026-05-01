from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


DATASETS_DIR = Path(__file__).parent / "datasets"

# Bundled-dataset names must be a single safe segment — letters, digits,
# underscore, dash, and an optional `.jsonl` suffix. Anything else is rejected
# before we touch the filesystem, so `../../etc/passwd` style strings never
# resolve to a real path.
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+(\.jsonl)?$")


class DatasetError(RuntimeError):
    pass


@dataclass
class EvalCaseSpec:
    case_id: str
    question: str
    category: str | None = None
    expected_documents: list[str] = field(default_factory=list)
    should_abstain: bool = False
    notes: str | None = None


def _resolve_path(dataset: str) -> Path:
    if not isinstance(dataset, str) or not _NAME_RE.match(dataset):
        raise DatasetError(
            f"Invalid dataset name {dataset!r}; expected a bundled name like 'medicare_starter'."
        )

    name = dataset if dataset.endswith(".jsonl") else f"{dataset}.jsonl"
    candidate = (DATASETS_DIR / name).resolve()

    # Defense in depth: even though _NAME_RE forbids `..`, double-check that
    # the resolved path stays inside DATASETS_DIR.
    try:
        candidate.relative_to(DATASETS_DIR.resolve())
    except ValueError as exc:
        raise DatasetError(f"Dataset resolves outside the bundled datasets directory.") from exc

    if not candidate.exists():
        raise DatasetError(f"Dataset not found: {dataset}")
    return candidate


def load_dataset(dataset: str) -> tuple[Path, list[EvalCaseSpec]]:
    path = _resolve_path(dataset)
    cases: list[EvalCaseSpec] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"{path.name}:{line_number} invalid JSON: {exc}") from exc

            try:
                cases.append(
                    EvalCaseSpec(
                        case_id=str(payload["id"]),
                        question=str(payload["question"]),
                        category=payload.get("category"),
                        expected_documents=list(payload.get("expected_documents") or []),
                        should_abstain=bool(payload.get("should_abstain", False)),
                        notes=payload.get("notes"),
                    )
                )
            except KeyError as exc:
                raise DatasetError(f"{path.name}:{line_number} missing key {exc}") from exc

    if not cases:
        raise DatasetError(f"Dataset {path.name} contained no cases")
    return path, cases
