from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import Chunk, Document
from app.services.chunking import ChunkDraft, chunk_pages
from app.services.embeddings import EmbeddingService
from app.services.pdf_parser import ParsedDocument, parse_pdf
from app.services.qdrant_index import QdrantIndexService
from app.services.storage import file_checksum, processed_document_path, raw_document_path, write_bytes, write_json


DATE_PATTERNS = [
    r"(effective date|effective)\s*[:\-]\s*([A-Za-z]+ \d{1,2}, \d{4})",
    r"(review date|review)\s*[:\-]\s*([A-Za-z]+ \d{1,2}, \d{4})",
]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _detect_document_type(text: str) -> str | None:
    lowered = text.lower()
    mapping = {
        "policy": ["policy"],
        "procedure": ["procedure", "workflow"],
        "manual": ["manual", "handbook"],
        "guideline": ["guideline", "standard operating procedure", "sop"],
    }
    for label, keywords in mapping.items():
        if any(keyword in lowered for keyword in keywords):
            return label
    return None


def _detect_department(text: str) -> str | None:
    lowered = text.lower()
    mapping = {
        "utilization_management": ["utilization management", "prior authorization"],
        "care_management": ["care management", "case management", "discharge"],
        "infection_control": ["infection control", "infectious disease"],
        "revenue_cycle": ["claims", "billing", "revenue cycle"],
        "telehealth": ["telehealth", "virtual visit"],
    }
    for label, keywords in mapping.items():
        if any(keyword in lowered for keyword in keywords):
            return label
    return None


def _detect_policy_status(text: str) -> str:
    lowered = text.lower()
    if "retired" in lowered or "superseded" in lowered:
        return "retired"
    if "draft" in lowered:
        return "draft"
    return "active"


def _detect_version(text: str) -> str | None:
    match = re.search(r"\b(?:version|revision|rev\.?)\b\s*[:\-]?\s*([A-Za-z0-9._-]+)", text, re.IGNORECASE)
    return match.group(2) if match else None


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


async def create_document_from_upload(db: Session, upload: UploadFile) -> Document:
    content = await upload.read()
    if not content:
        raise ValueError("Uploaded file is empty")

    document = Document(
        title=Path(upload.filename or "document.pdf").stem.replace("-", " ").replace("_", " ").title(),
        source_filename=upload.filename or "document.pdf",
        stored_path="",
        checksum=file_checksum(content),
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
    parsed = parse_pdf(Path(document.stored_path))
    combined_text = "\n\n".join(page.text for page in parsed.pages)

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

    chunks = chunk_pages(parsed.pages)
    if not chunks:
        raise ValueError("No chunkable text found in PDF")

    db.execute(delete(Chunk).where(Chunk.document_id == document.id))
    chunk_rows = _chunk_rows(document, chunks)
    db.add_all(chunk_rows)
    db.flush()

    embedding_service = EmbeddingService()
    embedding_batch = embedding_service.embed_many([chunk.text for chunk in chunk_rows])

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

    qdrant_index = QdrantIndexService()
    qdrant_index.replace_document_chunks(
        document_id=document.id,
        chunks=qdrant_chunks,
        vectors=embedding_batch.vectors,
    )

    write_json(processed_document_path(document.id), _artifact_payload(parsed, chunks))

    document.ingestion_status = "indexed"
    document.parse_error = None
    db.commit()
    db.refresh(document)
    return document, len(chunk_rows), embedding_batch.provider, embedding_batch.dimensions
