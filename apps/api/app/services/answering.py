from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas import AnswerCitation, AnswerResponse, ConfidenceInputs, QueryChunkResult, QueryFilters
from app.services.retrieval import RetrievalMode, RetrievalService

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


logger = logging.getLogger(__name__)


ConfidenceBucket = Literal["high", "medium", "low"]

_BUCKET_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
_RANK_BUCKET: dict[int, ConfidenceBucket] = {0: "low", 1: "medium", 2: "high"}

# Score thresholds tuned for cosine-normalized text-embedding-3-large vectors.
# These are conservative; revisit once the eval harness produces calibration data.
_STRONG_SCORE = 0.55
_OK_SCORE = 0.35


class AnswerCitationDraft(BaseModel):
    chunk_id: str = Field(description="Exact chunk_id of a retrieved evidence chunk that supports the answer.")
    support: str | None = Field(
        default=None,
        description="Short note (paraphrased) explaining what this chunk supports.",
    )
    quote: str | None = Field(
        default=None,
        description=(
            "The single most relevant verbatim phrase from the chunk's text that grounds the cited claim. "
            "Copy the words exactly as they appear in the chunk (no paraphrasing, no ellipsis, no quotes around it). "
            "Aim for one sentence or one clause; keep it under ~30 words."
        ),
    )


class AnswerDraft(BaseModel):
    answer: str = Field(description="Direct answer grounded only in the supplied evidence.")
    abstained: bool = Field(description="True when the evidence is insufficient to answer safely.")
    confidence: ConfidenceBucket = Field(
        description="Confidence based on evidence quality and consistency."
    )
    confidence_reasons: list[str] = Field(
        description="Short reasons explaining the confidence level or abstention."
    )
    citations: list[AnswerCitationDraft] = Field(
        description="Evidence chunks used to support the answer. Use only provided chunk ids."
    )
    suggested_questions: list[str] = Field(
        default_factory=list,
        description=(
            "Up to 3 short, useful follow-up questions a healthcare admin might ask next, "
            "grounded in the same retrieved evidence. Match the language of the user's question. "
            "Each must be self-contained (no pronouns referring to prior turns)."
        ),
    )


def evidence_confidence(
    citations: list[AnswerCitation],
    retrieved_chunks: list[QueryChunkResult],
) -> ConfidenceInputs:
    """Derive a confidence bucket from retrieval signals only.

    The model's self-reported confidence is taken as a ceiling elsewhere; this function
    is the floor: it cannot raise confidence beyond what evidence supports.
    """
    if not retrieved_chunks:
        return ConfidenceInputs(
            top_score=0.0,
            score_margin=0.0,
            unique_documents=0,
            citation_count=0,
            all_cited_active=False,
            evidence_bucket="low",
        )

    top_score = retrieved_chunks[0].score
    second_score = retrieved_chunks[1].score if len(retrieved_chunks) > 1 else 0.0
    score_margin = top_score - second_score

    citation_ids = {citation.chunk_id for citation in citations}
    cited_chunks = [chunk for chunk in retrieved_chunks if chunk.chunk_id in citation_ids]
    unique_documents = len({chunk.document_id for chunk in cited_chunks})

    known_statuses = [chunk.policy_status for chunk in cited_chunks if chunk.policy_status is not None]
    if not citations:
        all_cited_active = False
    elif not known_statuses:
        all_cited_active = False
    else:
        all_cited_active = all(status == "active" for status in known_statuses)

    bucket = _bucket_from_inputs(
        top_score=top_score,
        citation_count=len(citations),
        unique_documents=unique_documents,
        all_cited_active=all_cited_active,
    )

    return ConfidenceInputs(
        top_score=top_score,
        score_margin=score_margin,
        unique_documents=unique_documents,
        citation_count=len(citations),
        all_cited_active=all_cited_active,
        evidence_bucket=bucket,
    )


_INLINE_MARKER_RE = re.compile(
    r"\[(?:\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"(?:\s*[,;]\s*(?:\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}))*\]"
)


def sanitize_suggested_questions(raw: list[str] | None, *, limit: int = 3) -> list[str]:
    """Trim, dedupe, and cap follow-up suggestions before they leave the API."""
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def ensure_inline_citation_markers(answer: str, citation_count: int) -> str:
    """If the model produced citations but forgot to inline them, append `[1] [2]...`
    at the end so the frontend chip renderer has something to attach to.

    Recognized inline forms: numeric (`[1]`, `[2, 3]`) and UUID (`[abcd...]`,
    `[abcd...; efgh...]`). If any of those are already present, we leave the
    answer untouched.
    """
    if not answer or citation_count <= 0:
        return answer
    if _INLINE_MARKER_RE.search(answer):
        return answer
    appended = " ".join(f"[{i}]" for i in range(1, citation_count + 1))
    separator = " " if answer.endswith((".", "!", "?", ":")) else ". "
    return f"{answer.rstrip()}{separator}{appended}"


def _extract_token_usage(response: object) -> dict | None:
    """Pull token usage out of an OpenAI Responses API response defensively.

    Field names vary slightly across SDK versions; missing values are dropped.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    captured: dict = {}
    for key in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens"):
        value = getattr(usage, key, None)
        if value is not None:
            captured[key] = value
    return captured or None


def combine_confidence(model_bucket: ConfidenceBucket, evidence_bucket: ConfidenceBucket) -> ConfidenceBucket:
    """Take the lower of the model's self-report and the evidence-derived bucket.

    Evidence is the ceiling — the model can only ever downgrade itself, never inflate.
    """
    return _RANK_BUCKET[min(_BUCKET_RANK[model_bucket], _BUCKET_RANK[evidence_bucket])]


def _bucket_from_inputs(
    *,
    top_score: float,
    citation_count: int,
    unique_documents: int,
    all_cited_active: bool,
) -> ConfidenceBucket:
    if (
        top_score >= _STRONG_SCORE
        and citation_count >= 2
        and unique_documents >= 1
        and all_cited_active
    ):
        return "high"
    if top_score >= _OK_SCORE and citation_count >= 1:
        return "medium"
    return "low"


class AnsweringService:
    def __init__(self) -> None:
        self.retrieval_service = RetrievalService()
        self.answer_model = settings.openai_answer_model
        self.client = None
        if settings.openai_api_key and OpenAI is not None:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def retrieve(
        self,
        question: str,
        top_k: int,
        filters: QueryFilters | None = None,
        mode: RetrievalMode = "hybrid",
    ) -> tuple[str, list[QueryChunkResult]]:
        """Retrieval-only step. Exposed so streaming endpoints can emit retrieval
        events before composing the answer."""
        return self.retrieval_service.search(
            question=question,
            top_k=top_k,
            filters=filters,
            mode=mode,
        )

    def answer(
        self,
        question: str,
        top_k: int,
        filters: QueryFilters | None = None,
        mode: RetrievalMode = "hybrid",
    ) -> AnswerResponse:
        embedding_provider, retrieved_chunks = self.retrieve(question, top_k, filters, mode)
        return self.compose(
            question=question,
            top_k=top_k,
            embedding_provider=embedding_provider,
            retrieved_chunks=retrieved_chunks,
        )

    def compose(
        self,
        *,
        question: str,
        top_k: int,
        embedding_provider: str,
        retrieved_chunks: list[QueryChunkResult],
    ) -> AnswerResponse:
        """Compose an AnswerResponse from already-retrieved chunks.

        Same logic as answer() minus retrieval — used by both /api/answer and the
        streaming endpoint, where retrieval needs to be visible before composition.
        """
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
                confidence_inputs=evidence_confidence(citations=[], retrieved_chunks=[]),
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
                    "You are a healthcare policy assistant. Answer only from the supplied evidence.\n"
                    "Write the answer in concise markdown — use bullet lists for multi-item answers, "
                    "**bold** for important terms, short paragraphs otherwise. After every clause you "
                    "draw from a chunk, write a citation marker like [1] or [1, 2]. The numbers are "
                    "1-indexed positions in the citations array you return.\n"
                    "For each citation, include a `quote` field with the single most relevant VERBATIM "
                    "phrase copied exactly from that chunk's text — no paraphrasing, no quotation marks "
                    "around it, no ellipsis. Aim for one sentence or clause, under 30 words.\n"
                    "If the evidence is too thin to ground an answer, set abstained=true, return no "
                    "citations, and write one short sentence saying what's missing.\n"
                    "Also produce up to 3 `suggested_questions` — short, self-contained follow-up "
                    "questions a healthcare admin might ask next, anchored in the same retrieved "
                    "evidence. Match the language of the user's question (Dutch question → Dutch "
                    "suggestions). Do not repeat the user's question."
                ),
                input=prompt,
                text_format=AnswerDraft,
                # gpt-5 family includes reasoning tokens in this budget; 700 was
                # not enough headroom for both reasoning and a structured answer
                # with citations, leading to truncated JSON and parse failures.
                max_output_tokens=2500,
                store=False,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("Structured answer generation returned no parsed output.")

            token_usage = _extract_token_usage(response)
            citations = self._citation_records(parsed.citations, retrieved_chunks)

            # Abstention path: model abstained OR no grounded citations made it through.
            # Either way, do not decorate with fallback citations and force confidence low.
            if parsed.abstained or not citations:
                confidence_inputs = evidence_confidence(citations=[], retrieved_chunks=retrieved_chunks)
                reasons = parsed.confidence_reasons or [
                    "Model abstained or returned no citations grounded in the retrieved evidence."
                ]
                return AnswerResponse(
                    question=question,
                    answer=parsed.answer.strip(),
                    abstained=True,
                    confidence="low",
                    confidence_reasons=reasons,
                    answer_model=self.answer_model,
                    embedding_provider=embedding_provider,
                    top_k=top_k,
                    citations=[],
                    retrieved_chunks=retrieved_chunks,
                    confidence_inputs=confidence_inputs,
                    token_usage=token_usage,
                    suggested_questions=sanitize_suggested_questions(parsed.suggested_questions),
                )

            confidence_inputs = evidence_confidence(citations=citations, retrieved_chunks=retrieved_chunks)
            combined = combine_confidence(parsed.confidence, confidence_inputs.evidence_bucket)

            confidence_reasons = parsed.confidence_reasons or [
                "The answer was generated from retrieved policy evidence."
            ]
            if combined != parsed.confidence:
                confidence_reasons = [
                    *confidence_reasons,
                    f"Downgraded from model self-report ({parsed.confidence}) by evidence signals "
                    f"(top score {confidence_inputs.top_score:.2f}, "
                    f"{confidence_inputs.citation_count} citations across "
                    f"{confidence_inputs.unique_documents} document"
                    f"{'' if confidence_inputs.unique_documents == 1 else 's'}).",
                ]

            return AnswerResponse(
                question=question,
                answer=ensure_inline_citation_markers(parsed.answer.strip(), len(citations)),
                abstained=False,
                confidence=combined,
                confidence_reasons=confidence_reasons,
                answer_model=self.answer_model,
                embedding_provider=embedding_provider,
                top_k=top_k,
                citations=citations,
                retrieved_chunks=retrieved_chunks,
                confidence_inputs=confidence_inputs,
                token_usage=token_usage,
                suggested_questions=sanitize_suggested_questions(parsed.suggested_questions),
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
        top_chunk = retrieved_chunks[0]
        compact = " ".join(top_chunk.text.split())
        if len(compact) > 480:
            answer = compact[:480].rstrip() + "..."
        else:
            answer = compact

        citation = AnswerCitation(
            chunk_id=top_chunk.chunk_id,
            document_id=top_chunk.document_id,
            document_title=top_chunk.document_title,
            source_filename=top_chunk.source_filename,
            section_path=top_chunk.section_path,
            page_start=top_chunk.page_start,
            page_end=top_chunk.page_end,
            score=top_chunk.score,
            quote_preview=self._quote_preview(top_chunk.text),
            support="Top retrieved chunk used as the extractive source (no LLM available).",
        )
        citations = [citation]
        confidence_inputs = evidence_confidence(citations=citations, retrieved_chunks=retrieved_chunks)

        return AnswerResponse(
            question=question,
            answer=answer,
            abstained=False,
            confidence=confidence_inputs.evidence_bucket,
            confidence_reasons=[
                "Extractive top-1 chunk; LLM answer generation is unavailable.",
                f"Top retrieval score {confidence_inputs.top_score:.2f} with "
                f"{confidence_inputs.citation_count} citation"
                f"{'' if confidence_inputs.citation_count == 1 else 's'}.",
            ],
            answer_model="local-extractive",
            embedding_provider=embedding_provider,
            top_k=top_k,
            citations=citations,
            retrieved_chunks=retrieved_chunks,
            confidence_inputs=confidence_inputs,
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
            + "\n\nRespond with a concise grounded answer and cite only chunk ids from the evidence above. "
            "If you cannot ground the answer in these chunks, set abstained=true and return no citations."
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
            quote = (draft.quote or "").strip() or None
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
                    quote=quote,
                )
            )

        return citations

    def _quote_preview(self, text: str, max_length: int = 320) -> str:
        compact = " ".join(text.split())
        if len(compact) <= max_length:
            return compact
        return compact[: max_length - 3].rstrip() + "..."
