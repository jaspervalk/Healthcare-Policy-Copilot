from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class ParsedPage:
    page_number: int
    text: str


@dataclass
class ParsedDocument:
    title: str
    page_count: int
    pages: list[ParsedPage]
    metadata: dict[str, str]


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _first_non_empty_line(text: str) -> str | None:
    for line in text.splitlines():
        candidate = normalize_text(line)
        if candidate:
            return candidate
    return None


def _last_non_empty_line(text: str) -> str | None:
    for line in reversed(text.splitlines()):
        candidate = normalize_text(line)
        if candidate:
            return candidate
    return None


def _common_edge_lines(page_texts: list[str], extractor, min_pages: int = 3) -> set[str]:
    values = [value for text in page_texts if (value := extractor(text))]
    counts = Counter(values)
    threshold = max(min_pages, len(page_texts) // 2)
    return {line for line, count in counts.items() if count >= threshold}


def _strip_common_headers_and_footers(page_texts: list[str]) -> list[str]:
    headers = _common_edge_lines(page_texts, _first_non_empty_line)
    footers = _common_edge_lines(page_texts, _last_non_empty_line)
    cleaned_pages: list[str] = []

    for text in page_texts:
        lines = [normalize_text(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        if lines and lines[0] in headers:
            lines = lines[1:]
        if lines and lines[-1] in footers:
            lines = lines[:-1]
        cleaned_pages.append("\n".join(lines).strip())

    return cleaned_pages


def _infer_title(metadata: dict[str, str], page_texts: list[str], file_path: Path) -> str:
    for key in ("Title", "title"):
        value = metadata.get(key)
        if value:
            return normalize_text(value)

    for text in page_texts:
        for line in text.splitlines():
            candidate = normalize_text(line)
            if candidate and len(candidate.split()) <= 18:
                return candidate

    return file_path.stem.replace("-", " ").replace("_", " ").title()


def parse_pdf(file_path: Path) -> ParsedDocument:
    reader = PdfReader(str(file_path))
    raw_metadata = {str(key).lstrip("/"): str(value) for key, value in dict(reader.metadata or {}).items()}
    page_texts = [page.extract_text() or "" for page in reader.pages]
    page_texts = _strip_common_headers_and_footers(page_texts)

    pages = [
        ParsedPage(page_number=index + 1, text=normalize_text(text))
        for index, text in enumerate(page_texts)
        if normalize_text(text)
    ]

    title = _infer_title(raw_metadata, [page.text for page in pages], file_path)
    return ParsedDocument(
        title=title,
        page_count=len(reader.pages),
        pages=pages,
        metadata=raw_metadata,
    )

