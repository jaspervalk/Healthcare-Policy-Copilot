from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


DATASETS_DIR = Path(__file__).parent / "datasets"


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
    candidate = Path(dataset)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    bundled = DATASETS_DIR / f"{dataset}.jsonl"
    if bundled.exists():
        return bundled
    bundled_named = DATASETS_DIR / dataset
    if bundled_named.exists():
        return bundled_named
    raise DatasetError(f"Dataset not found: {dataset}")


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
