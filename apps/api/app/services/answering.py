from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas import AnswerCitation, AnswerResponse, QueryChunkResult, QueryFilters
from app.services.retrieval import RetrievalService

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


logger = logging.getLogger(__name__)


class AnswerCitationDraft(BaseModel):
    chunk_id: str = Field(description="Exact chunk_id of a retrieved evidence chunk that supports the answer.")
    support: str | None = Field(
        default=None,
        description="Short note explaining what this chunk supports.",
    )


class AnswerDraft(BaseModel):
    answer: str = Field(description="Direct answer grounded only in the supplied evidence.")
    abstained: bool = Field(description="True when the evidence is insufficient to answer safely.")
    confidence: Literal["high", "medium", "low"] = Field(
        description="Confidence based on evidence quality and consistency."
    )
    confidence_reasons: list[str] = Field(
        description="Short reasons explaining the confidence level or abstention."
    )
    citations: list[AnswerCitationDraft] = Field(
        description="Evidence chunks used to support the answer. Use only provided chunk ids."
    )


class AnsweringService:
    def __init__(self) -> None:
        self.retrieval_service = RetrievalService()
        self.answer_model = settings.openai_answer_model
        self.client = None
        if settings.openai_api_key and OpenAI is not None:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def answer(self, question: str, top_k: int, filters: QueryFilters | None = None) -> AnswerResponse:
        embedding_provider, retrieved_chunks = self.retrieval_service.search(
            question=question,
            top_k=top_k,
            filters=filters,
        )

        if not retrieved_chunks:
            return AnswerResponse(
                question=question,
                answer="I could not find enough indexed policy evidence to answer that question yet.",
                abstained=True,
                confidence="low",
                confidence_reasons=["No relevant chunks were retrieved from the indexed policy corpus."],
                answer_model="none",
                embedding_provider=embedding_provider,
                top_k=top_k,
                citations=[],
                retrieved_chunks=[],
            )

        if self.client is None:
            return self._fallback_answer(
                question=question,
                top_k=top_k,
                embedding_provider=embedding_provider,
                retrieved_chunks=retrieved_chunks,
            )

        try:
            prompt = self._build_prompt(question=question, retrieved_chunks=retrieved_chunks)
            response = self.client.responses.parse(
                model=self.answer_model,
                instructions=(
                    "You are a healthcare policy assistant. Answer only from the supplied evidence. "
                    "Do not invent policy details. If the evidence is incomplete or ambiguous, abstain clearly. "
                    "Only cite chunk ids that are explicitly provided in the evidence list."
                ),
                input=prompt,
                text_format=AnswerDraft,
                max_output_tokens=700,
                temperature=0.1,
                store=False,
                text={"verbosity": "low"},
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("Structured answer generation returned no parsed output.")

            citations = self._citation_records(parsed.citations, retrieved_chunks)
            if not citations and retrieved_chunks:
                citations = self._fallback_citations(retrieved_chunks)

            confidence = parsed.confidence if citations else "low"
            confidence_reasons = parsed.confidence_reasons or []
            if not confidence_reasons:
                confidence_reasons = ["The answer was generated from retrieved policy evidence."]

            return AnswerResponse(
                question=question,
                answer=parsed.answer.strip(),
                abstained=parsed.abstained,
                confidence=confidence,
                confidence_reasons=confidence_reasons,
                answer_model=self.answer_model,
                embedding_provider=embedding_provider,
                top_k=top_k,
                citations=citations,
                retrieved_chunks=retrieved_chunks,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Falling back to extractive answer mode: %s", exc)
            return self._fallback_answer(
                question=question,
                top_k=top_k,
                embedding_provider=embedding_provider,
                retrieved_chunks=retrieved_chunks,
            )

    def _fallback_answer(
        self,
        *,
        question: str,
        top_k: int,
        embedding_provider: str,
        retrieved_chunks: list[QueryChunkResult],
    ) -> AnswerResponse:
        citations = self._fallback_citations(retrieved_chunks)
        top_chunk = retrieved_chunks[0]
        answer = (
            "I do not have answer generation enabled, so this is an evidence-first fallback. "
            f"The strongest retrieved policy chunk is from {top_chunk.document_title}"
        )
        if top_chunk.section_path:
            answer += f", section {top_chunk.section_path}"
        answer += f", pages {top_chunk.page_start}-{top_chunk.page_end}. "
        answer += top_chunk.text[:320].strip()
        if len(top_chunk.text) > 320:
            answer += "..."

        return AnswerResponse(
            question=question,
            answer=answer,
            abstained=False,
            confidence="medium" if citations else "low",
            confidence_reasons=[
                "This is a fallback extractive summary derived from the top retrieved evidence chunk.",
            ],
            answer_model="local-extractive",
            embedding_provider=embedding_provider,
            top_k=top_k,
            citations=citations,
            retrieved_chunks=retrieved_chunks,
        )

    def _build_prompt(self, *, question: str, retrieved_chunks: list[QueryChunkResult]) -> str:
        evidence_blocks = []
        for chunk in retrieved_chunks:
            evidence_blocks.append(
                "\n".join(
                    [
                        f"chunk_id: {chunk.chunk_id}",
                        f"title: {chunk.document_title}",
                        f"source_filename: {chunk.source_filename}",
                        f"section_path: {chunk.section_path or 'General section'}",
                        f"pages: {chunk.page_start}-{chunk.page_end}",
                        f"score: {chunk.score:.3f}",
                        "text:",
                        chunk.text,
                    ]
                )
            )

        return (
            f"Question:\n{question}\n\n"
            "Retrieved evidence chunks:\n\n"
            + "\n\n---\n\n".join(evidence_blocks)
            + "\n\nRespond with a concise grounded answer and cite only chunk ids from the evidence above."
        )

    def _citation_records(
        self,
        citation_drafts: list[AnswerCitationDraft],
        retrieved_chunks: list[QueryChunkResult],
    ) -> list[AnswerCitation]:
        by_chunk_id = {chunk.chunk_id: chunk for chunk in retrieved_chunks}
        seen: set[str] = set()
        citations: list[AnswerCitation] = []

        for draft in citation_drafts:
            chunk = by_chunk_id.get(draft.chunk_id)
            if chunk is None or chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            citations.append(
                AnswerCitation(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    document_title=chunk.document_title,
                    source_filename=chunk.source_filename,
                    section_path=chunk.section_path,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    score=chunk.score,
                    quote_preview=self._quote_preview(chunk.text),
                    support=draft.support,
                )
            )

        return citations

    def _fallback_citations(self, retrieved_chunks: list[QueryChunkResult]) -> list[AnswerCitation]:
        return [
            AnswerCitation(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                source_filename=chunk.source_filename,
                section_path=chunk.section_path,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                score=chunk.score,
                quote_preview=self._quote_preview(chunk.text),
                support="High-similarity retrieved evidence chunk.",
            )
            for chunk in retrieved_chunks[:2]
        ]

    def _quote_preview(self, text: str, max_length: int = 320) -> str:
        compact = " ".join(text.split())
        if len(compact) <= max_length:
            return compact
        return compact[: max_length - 3].rstrip() + "..."
