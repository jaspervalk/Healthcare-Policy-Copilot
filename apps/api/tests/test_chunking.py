from app.services.chunking import chunk_pages
from app.services.pdf_parser import ParsedPage


def test_chunk_pages_preserves_headings_and_overlap():
    pages = [
        ParsedPage(
            page_number=1,
            text=(
                "UTILIZATION REVIEW POLICY\n\n"
                "1. Prior Authorization\n\n"
                + "Urgent requests require clinical review. " * 80
            ),
        ),
        ParsedPage(
            page_number=2,
            text=(
                "1. Prior Authorization\n\n"
                + "Escalations are routed to the medical director. " * 70
            ),
        ),
    ]

    chunks = chunk_pages(pages, target_words=120, overlap_words=20)

    assert len(chunks) >= 2
    assert all(chunk.section_path == "1. Prior Authorization" for chunk in chunks)
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2

