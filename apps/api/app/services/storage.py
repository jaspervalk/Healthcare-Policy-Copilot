from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.core.config import settings


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", filename).strip("-")
    return cleaned or "document.pdf"


def file_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def raw_document_path(document_id: str, filename: str) -> Path:
    return settings.raw_documents_dir / f"{document_id}-{sanitize_filename(filename)}"


def processed_document_path(document_id: str) -> Path:
    return settings.processed_documents_dir / f"{document_id}.json"

