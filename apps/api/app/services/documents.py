from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import Chunk, Document
from app.services.chunking import ChunkDraft, chunk_pages
from app.services.embeddings import EmbeddingService
from app.services.hybrid_index import refresh_hybrid_index
from app.services.index_stamp import read_stamp, validate_or_raise, write_stamp
from app.services.pdf_parser import ParsedDocument, parse_pdf
from app.services.qdrant_index import QdrantIndexService
from app.services.storage import delete_path, file_checksum, processed_document_path, raw_document_path, write_bytes, write_json


DATE_PATTERNS = [
    r"(effective date|effective)\s*[:\-]\s*([A-Za-z]+ \d{1,2}, \d{4})",
    r"(review date|review)\s*[:\-]\s*([A-Za-z]+ \d{1,2}, \d{4})",
]


@dataclass
class DeletedDocumentResult:
    document_id: str
    title: str
    deleted_chunk_count: int
    removed_from_index: bool
    raw_file_deleted: bool
    processed_artifact_deleted: bool


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _score_keywords(text: str, keywords: list[str]) -> int:
    """Sum word-boundary occurrences of each keyword in `text` (already lowercased).

    Word boundaries prevent 'policymaker' from matching 'policy', which was the
    failure mode of the previous substring check.
    """
    total = 0
    for keyword in keywords:
        # Word-boundary match. Multi-word keywords (e.g. 'standard operating procedure')
        # treat internal whitespace literally; that's what we want.
        pattern = r"\b" + re.escape(keyword) + r"\b"
        total += len(re.findall(pattern, text))
    return total


def _detect_document_type(text: str) -> str | None:
    """Pick the document type with the most word-boundary keyword matches.

    Replaces the previous insertion-order priority that misclassified any
    procedure mentioning 'policy' as a policy.
    """
    lowered = text.lower()
    mapping = {
        "policy": ["policy"],
        "procedure": ["procedure", "workflow"],
        "manual": ["manual", "handbook"],
        "guideline": ["guideline", "standard operating procedure", "sop"],
    }
    best_label: str | None = None
    best_score = 0
    for label, keywords in mapping.items():
        score = _score_keywords(lowered, keywords)
        if score > best_score:
            best_label = label
            best_score = score
    return best_label


def _detect_department(text: str) -> str | None:
    lowered = text.lower()
    mapping = {
        "utilization_management": ["utilization management", "prior authorization"],
        "care_management": ["care management", "case management", "discharge"],
        "infection_control": ["infection control", "infectious disease"],
        "revenue_cycle": ["claims", "billing", "revenue cycle"],
        "telehealth": ["telehealth", "virtual visit"],
    }
    best_label: str | None = None
    best_score = 0
    for label, keywords in mapping.items():
        score = _score_keywords(lowered, keywords)
        if score > best_score:
            best_label = label
            best_score = score
    return best_label


def _detect_policy_status(text: str) -> str | None:
    """Return the detected status, or None when no signal is present.

    Previously defaulted to 'active' on every document — a confident claim from
    no evidence. None means 'unknown' and the UI can render that explicitly.
    """
    lowered = text.lower()
    if re.search(r"\b(retired|superseded)\b", lowered):
        return "retired"
    if re.search(r"\bdraft\b", lowered):
        return "draft"
    if re.search(r"\b(active|effective|current)\b", lowered):
        return "active"
    return None


def _detect_version(text: str) -> str | None:
    match = re.search(r"\b(?:version|revision|rev\.?)\b\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9._-]*)", text, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_date(label: str, text: str) -> date | None:
    match = re.search(rf"{label}\s*[:\-]\s*([A-Za-z]+ \d{{1,2}}, \d{{4}})", text, re.IGNORECASE)
    if not match:
        return None
    return _parse_date(match.group(1))


def _artifact_payload(parsed: ParsedDocument, chunks: list[ChunkDraft]) -> dict:
    return {
        "title": parsed.title,
        "page_count": parsed.page_count,
        "metadata": parsed.metadata,
        "pages": [{"page_number": page.page_number, "text": page.text} for page in parsed.pages],
        "chunks": [chunk.to_payload() for chunk in chunks],
    }


def list_documents(db: Session) -> list[Document]:
    stmt = select(Document).options(selectinload(Document.chunks)).order_by(Document.created_at.desc())
    return list(db.scalars(stmt).all())


def get_document(db: Session, document_id: str) -> Document | None:
    stmt = select(Document).options(selectinload(Document.chunks)).where(Document.id == document_id)
    return db.scalar(stmt)


def find_document_by_checksum(db: Session, checksum: str) -> Document | None:
    stmt = select(Document).options(selectinload(Document.chunks)).where(Document.checksum == checksum)
    return db.scalar(stmt)


_PATCHABLE_FIELDS = {
    "title",
    "document_type",
    "department",
    "policy_status",
    "version_label",
    "effective_date",
    "review_date",
}


def update_document_metadata(db: Session, document: Document, updates: dict) -> Document:
    """Apply a partial metadata update. Only whitelisted fields are accepted."""
    for field, value in updates.items():
        if field not in _PATCHABLE_FIELDS:
            raise ValueError(f"Field '{field}' is not editable.")
        setattr(document, field, value)
    db.commit()
    db.refresh(document)
    return document


async def create_document_from_upload(db: Session, upload: UploadFile) -> Document:
    from app.api.errors import DuplicateDocumentError
    from app.services.upload_safety import validate_upload

    content = await upload.read()
    validate_upload(content)

    checksum = file_checksum(content)
    existing = find_document_by_checksum(db, checksum)
    if existing is not None:
        raise DuplicateDocumentError(existing_document_id=existing.id, title=existing.title)

    document = Document(
        title=Path(upload.filename or "document.pdf").stem.replace("-", " ").replace("_", " ").title(),
        source_filename=upload.filename or "document.pdf",
        stored_path="",
        checksum=checksum,
        ingestion_status="uploaded",
        extracted_metadata={},
    )
    db.add(document)
    db.flush()

    destination = raw_document_path(document.id, document.source_filename)
    write_bytes(destination, content)
    document.stored_path = str(destination)
    db.commit()
    db.refresh(document)
    return document


def _chunk_rows(document: Document, chunks: list[ChunkDraft]) -> list[Chunk]:
    return [
        Chunk(
            document_id=document.id,
            chunk_index=chunk.chunk_index,
            section_path=chunk.section_path,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            token_count=chunk.token_count,
            text=chunk.text,
            normalized_text=chunk.normalized_text,
            chunk_metadata=chunk.chunk_metadata,
        )
        for chunk in chunks
    ]


def index_document(db: Session, document: Document) -> tuple[Document, int, str, int]:
    """Atomic-ish indexing pipeline.

    Order: parse → chunk → embed (all in memory, no SQL/Qdrant writes yet) →
    validate stamp → SQL writes → Qdrant upsert → SQL commit + write stamp →
    processed JSON. On Qdrant failure we rollback SQL and best-effort delete
    any partial Qdrant points for this document.
    """
    # --- in-memory phase: nothing persisted yet ---
    parsed = parse_pdf(Path(document.stored_path))
    combined_text = "\n\n".join(page.text for page in parsed.pages)

    chunk_drafts = chunk_pages(parsed.pages)
    if not chunk_drafts:
        raise ValueError("No chunkable text found in PDF")

    embedding_service = EmbeddingService()
    embedding_batch = embedding_service.embed_many([chunk.text for chunk in chunk_drafts])

    qdrant_index = QdrantIndexService()
    stamp = read_stamp(db, qdrant_index.collection_name)
    validate_or_raise(
        stamp,
        provider=embedding_batch.provider,
        model=embedding_batch.model,
        dimensions=embedding_batch.dimensions,
    )

    # --- SQL writes (still uncommitted) ---
    document.title = parsed.title
    document.page_count = parsed.page_count
    document.document_type = document.document_type or _detect_document_type(f"{parsed.title}\n{combined_text}")
    document.department = document.department or _detect_department(combined_text)
    document.policy_status = document.policy_status or _detect_policy_status(combined_text)
    document.effective_date = document.effective_date or _extract_date("effective date", combined_text)
    document.review_date = document.review_date or _extract_date("review date", combined_text)
    document.version_label = document.version_label or _detect_version(combined_text)
    document.extracted_metadata = {
        "pdf_metadata": parsed.metadata,
        "inferred_document_type": document.document_type,
        "inferred_department": document.department,
        "inferred_policy_status": document.policy_status,
    }

    db.execute(delete(Chunk).where(Chunk.document_id == document.id))
    chunk_rows = _chunk_rows(document, chunk_drafts)
    db.add_all(chunk_rows)
    db.flush()

    qdrant_chunks = [
        {
            "id": chunk.id,
            "document_title": document.title,
            "source_filename": document.source_filename,
            "department": document.department,
            "document_type": document.document_type,
            "policy_status": document.policy_status,
            "section_path": chunk.section_path,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "text": chunk.text,
            "chunk_metadata": chunk.chunk_metadata,
        }
        for chunk in chunk_rows
    ]

    # --- Qdrant upsert (point of no easy return) ---
    try:
        qdrant_index.upsert_chunks(
            document_id=document.id,
            chunks=qdrant_chunks,
            vectors=embedding_batch.vectors,
        )
    except Exception:
        db.rollback()
        # Best-effort: scrub any points that landed before the failure.
        try:
            qdrant_index.delete_document_chunks(document.id)
        except Exception:
            pass
        raise

    # --- finalize ---
    write_stamp(
        db,
        name=qdrant_index.collection_name,
        provider=embedding_batch.provider,
        model=embedding_batch.model,
        dimensions=embedding_batch.dimensions,
    )

    write_json(processed_document_path(document.id), _artifact_payload(parsed, chunk_drafts))

    document.ingestion_status = "indexed"
    document.parse_error = None
    try:
        db.commit()
    except Exception:
        db.rollback()
        # SQL commit failed after Qdrant upsert succeeded — revert Qdrant.
        try:
            qdrant_index.delete_document_chunks(document.id)
        except Exception:
            pass
        raise
    db.refresh(document)
    refresh_hybrid_index(db)
    return document, len(chunk_rows), embedding_batch.provider, embedding_batch.dimensions


def delete_document(db: Session, document: Document) -> DeletedDocumentResult:
    document_id = document.id
    title = document.title
    deleted_chunk_count = len(document.chunks)
    stored_path = Path(document.stored_path) if document.stored_path else None
    processed_path = processed_document_path(document.id)
    removed_from_index = document.ingestion_status == "indexed" or deleted_chunk_count > 0

    try:
        QdrantIndexService().delete_document_chunks(document_id)
    except Exception as exc:
        raise RuntimeError(f"Failed to remove vector index entries for {title}: {exc}") from exc

    db.delete(document)
    db.commit()

    raw_file_deleted = delete_path(stored_path) if stored_path is not None else False
    processed_artifact_deleted = delete_path(processed_path)

    refresh_hybrid_index(db)

    return DeletedDocumentResult(
        document_id=document_id,
        title=title,
        deleted_chunk_count=deleted_chunk_count,
        removed_from_index=removed_from_index,
        raw_file_deleted=raw_file_deleted,
        processed_artifact_deleted=processed_artifact_deleted,
    )
