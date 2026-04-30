import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Chunk, Document
from app.services.hybrid_index import HybridIndex, rrf_fuse, tokenize


def _setup_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'hybrid.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _seed(db, *, document_id: str, status: str, chunks: list[tuple[str, str]]) -> None:
    document = Document(
        id=document_id,
        title=f"Doc {document_id}",
        source_filename=f"{document_id}.pdf",
        stored_path=f"/tmp/{document_id}.pdf",
        checksum=f"hash-{document_id}",
        ingestion_status=status,
        extracted_metadata={},
        page_count=1,
    )
    db.add(document)
    db.flush()
    for chunk_id, text in chunks:
        db.add(
            Chunk(
                id=chunk_id,
                document_id=document_id,
                chunk_index=0,
                section_path=None,
                page_start=1,
                page_end=1,
                token_count=len(text.split()),
                text=text,
                normalized_text=text.lower(),
                chunk_metadata={},
            )
        )
    db.commit()


def test_tokenize_drops_stopwords_and_punctuation():
    tokens = tokenize("The Urgent Prior Authorization is required.")
    assert "urgent" in tokens
    assert "prior" in tokens
    assert "authorization" in tokens
    assert "the" not in tokens
    assert "is" not in tokens


def test_hybrid_index_only_includes_indexed_documents(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    with SessionLocal() as db:
        _seed(db, document_id="d1", status="indexed", chunks=[("c1", "urgent prior authorization escalation")])
        _seed(db, document_id="d2", status="failed", chunks=[("c2", "medicare benefit period")])

    index = HybridIndex()
    with SessionLocal() as db:
        size = index.rebuild_from_sql(db)
    assert size == 1
    assert index.ready

    hits = index.search("urgent authorization", limit=5)
    assert hits[0][0] == "c1"


def test_hybrid_index_returns_empty_for_empty_corpus(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    index = HybridIndex()
    with SessionLocal() as db:
        size = index.rebuild_from_sql(db)
    assert size == 0
    assert not index.ready
    assert index.search("anything", limit=5) == []


def test_hybrid_index_ranks_keyword_match_higher(tmp_path):
    SessionLocal = _setup_db(tmp_path)
    with SessionLocal() as db:
        _seed(
            db,
            document_id="d1",
            status="indexed",
            chunks=[
                ("c1", "lifetime reserve days are limited under medicare"),
                ("c2", "inpatient psychiatric coverage is restricted"),
                ("c3", "general overview of eligibility rules"),
            ],
        )

    index = HybridIndex()
    with SessionLocal() as db:
        index.rebuild_from_sql(db)

    hits = index.search("lifetime reserve days", limit=3)
    assert hits[0][0] == "c1"
    assert hits[0][1] > 0


def test_rrf_fuse_combines_overlapping_rankings():
    dense = [("a", 0.9), ("b", 0.8), ("c", 0.7)]
    sparse = [("c", 12.0), ("a", 6.0)]

    fused = rrf_fuse(dense, sparse, k=10)
    fused_ids = [chunk_id for chunk_id, _ in fused]

    # 'a' and 'c' both appear in both lists -> rank higher than 'b'.
    assert fused_ids.index("a") < fused_ids.index("b")
    assert fused_ids.index("c") < fused_ids.index("b")


def test_rrf_fuse_handles_disjoint_inputs():
    dense = [("a", 0.9)]
    sparse = [("b", 1.0)]
    fused = rrf_fuse(dense, sparse)
    assert {chunk_id for chunk_id, _ in fused} == {"a", "b"}
