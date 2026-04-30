from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.auth import require_admin_token
from app.api.errors import map_exception
from app.db import get_db
from app.schemas import (
    DeleteDocumentResponse,
    DocumentMetadataUpdate,
    DocumentRead,
    IndexDocumentResponse,
    UploadDocumentResponse,
)
from app.services.documents import (
    create_document_from_upload,
    delete_document,
    get_document,
    index_document,
    list_documents,
    update_document_metadata,
)


router = APIRouter()


def _document_payload(document) -> DocumentRead:
    return DocumentRead.model_validate(document).model_copy(update={"chunk_count": len(document.chunks)})


def _index_payload(document, chunk_count: int, provider: str, dimensions: int) -> IndexDocumentResponse:
    return IndexDocumentResponse(
        document=_document_payload(document),
        chunk_count=chunk_count,
        embedding_provider=provider,
        embedding_dimensions=dimensions,
    )


def _mark_document_failed(db: Session, document_id: str, error_message: str) -> None:
    db.rollback()
    document = get_document(db, document_id)
    if document is not None:
        document.ingestion_status = "failed"
        document.parse_error = error_message
        db.commit()


@router.get("", response_model=list[DocumentRead])
def get_documents(db: Session = Depends(get_db)) -> list[DocumentRead]:
    return [_document_payload(document) for document in list_documents(db)]


@router.get("/{document_id}", response_model=DocumentRead)
def get_document_by_id(document_id: str, db: Session = Depends(get_db)) -> DocumentRead:
    document = get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _document_payload(document)


@router.post("/upload", response_model=UploadDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadDocumentResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only PDF uploads are supported")

    document = None
    try:
        document = await create_document_from_upload(db, file)
        indexed_document, chunk_count, provider, dimensions = index_document(db, document)
        return UploadDocumentResponse(
            document=_document_payload(indexed_document),
            auto_indexed=True,
            chunk_count=chunk_count,
            embedding_provider=provider,
            embedding_dimensions=dimensions,
        )
    except Exception as exc:
        if document is not None:
            _mark_document_failed(db, document.id, str(exc))
        raise map_exception(exc) from exc


@router.post("/{document_id}/index", response_model=IndexDocumentResponse)
def index_document_by_id(document_id: str, db: Session = Depends(get_db)) -> IndexDocumentResponse:
    document = get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        indexed_document, chunk_count, provider, dimensions = index_document(db, document)
        return _index_payload(indexed_document, chunk_count, provider, dimensions)
    except Exception as exc:
        _mark_document_failed(db, document_id, str(exc))
        raise map_exception(exc) from exc


@router.patch("/{document_id}", response_model=DocumentRead)
def patch_document_metadata(
    document_id: str,
    update: DocumentMetadataUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_token),
) -> DocumentRead:
    document = get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    updates = update.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update; provide at least one editable field.",
        )

    try:
        updated = update_document_metadata(db, document, updates)
    except Exception as exc:
        db.rollback()
        raise map_exception(exc) from exc

    return _document_payload(updated)


@router.delete("/{document_id}", response_model=DeleteDocumentResponse)
def delete_document_by_id(
    document_id: str,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_token),
) -> DeleteDocumentResponse:
    document = get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        deleted = delete_document(db, document)
        return DeleteDocumentResponse(
            document_id=deleted.document_id,
            title=deleted.title,
            deleted_chunk_count=deleted.deleted_chunk_count,
            removed_from_index=deleted.removed_from_index,
            raw_file_deleted=deleted.raw_file_deleted,
            processed_artifact_deleted=deleted.processed_artifact_deleted,
        )
    except Exception as exc:
        db.rollback()
        raise map_exception(exc) from exc
