from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import DocumentRead, IndexDocumentResponse, UploadDocumentResponse
from app.services.documents import create_document_from_upload, get_document, index_document, list_documents


router = APIRouter()


def _document_payload(document) -> DocumentRead:
    return DocumentRead.model_validate(document).model_copy(update={"chunk_count": len(document.chunks)})


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

    try:
        document = await create_document_from_upload(db, file)
        return UploadDocumentResponse(document=_document_payload(document))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/{document_id}/index", response_model=IndexDocumentResponse)
def index_document_by_id(document_id: str, db: Session = Depends(get_db)) -> IndexDocumentResponse:
    document = get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    try:
        indexed_document, chunk_count, provider, dimensions = index_document(db, document)
        return IndexDocumentResponse(
            document=_document_payload(indexed_document),
            chunk_count=chunk_count,
            embedding_provider=provider,
            embedding_dimensions=dimensions,
        )
    except Exception as exc:
        db.rollback()
        document = get_document(db, document_id)
        if document is not None:
            document.ingestion_status = "failed"
            document.parse_error = str(exc)
            db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
