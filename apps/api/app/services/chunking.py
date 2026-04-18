from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from app.services.pdf_parser import ParsedPage, normalize_text


TARGET_WORDS = 425
OVERLAP_WORDS = 75


@dataclass
class ChunkDraft:
    chunk_index: int
    section_path: str | None
    page_start: int
    page_end: int
    token_count: int
    text: str
    normalized_text: str
    chunk_metadata: dict

    def to_payload(self) -> dict:
        return asdict(self)


@dataclass
class TextBlock:
    heading: str | None
    text: str
    page_number: int


def _looks_like_heading(block: str) -> bool:
    compact = normalize_text(block)
    if not compact:
        return False
    if len(compact.split()) > 14:
        return False
    if re.match(r"^\d+(\.\d+)*\.?[\s:-]", compact):
        return True
    if compact.endswith(":"):
        return True
    uppercase_ratio = sum(1 for char in compact if char.isupper()) / max(1, sum(1 for char in compact if char.isalpha()))
    return uppercase_ratio > 0.7


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _split_blocks(pages: list[ParsedPage]) -> list[TextBlock]:
    blocks: list[TextBlock] = []
    current_heading: str | None = None

    for page in pages:
        raw_blocks = [normalize_text(block) for block in re.split(r"\n\s*\n", page.text) if normalize_text(block)]
        for raw_block in raw_blocks:
            if _looks_like_heading(raw_block):
                current_heading = raw_block
                continue
            blocks.append(TextBlock(heading=current_heading, text=raw_block, page_number=page.page_number))

    return blocks


def _window_words(words: list[str], start: int, stop: int) -> str:
    return " ".join(words[start:stop]).strip()


def chunk_pages(pages: list[ParsedPage], target_words: int = TARGET_WORDS, overlap_words: int = OVERLAP_WORDS) -> list[ChunkDraft]:
    blocks = _split_blocks(pages)
    if not blocks:
        return []

    chunks: list[ChunkDraft] = []
    current_heading: str | None = None
    current_blocks: list[TextBlock] = []
    chunk_index = 0

    def flush_group(group: list[TextBlock], heading: str | None, next_index: int) -> int:
        if not group:
            return next_index

        body_text = "\n\n".join(block.text for block in group)
        words = body_text.split()
        if not words:
            return next_index

        start = 0
        while start < len(words):
            stop = min(len(words), start + target_words)
            snippet = _window_words(words, start, stop)
            if heading:
                chunk_text = f"{heading}\n{snippet}".strip()
            else:
                chunk_text = snippet

            page_numbers = [block.page_number for block in group]
            chunks.append(
                ChunkDraft(
                    chunk_index=next_index,
                    section_path=heading,
                    page_start=min(page_numbers),
                    page_end=max(page_numbers),
                    token_count=_word_count(chunk_text),
                    text=chunk_text,
                    normalized_text=normalize_text(chunk_text.lower()),
                    chunk_metadata={
                        "heading": heading,
                        "page_span": [min(page_numbers), max(page_numbers)],
                    },
                )
            )
            next_index += 1

            if stop >= len(words):
                break
            start = max(0, stop - overlap_words)

        return next_index

    for block in blocks:
        if current_heading is None:
            current_heading = block.heading
        if current_blocks and block.heading != current_heading:
            chunk_index = flush_group(current_blocks, current_heading, chunk_index)
            current_blocks = []
            current_heading = block.heading
        current_blocks.append(block)

    chunk_index = flush_group(current_blocks, current_heading, chunk_index)
    return chunks
