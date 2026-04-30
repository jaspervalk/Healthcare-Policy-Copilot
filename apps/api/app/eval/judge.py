from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas import QueryChunkResult

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


logger = logging.getLogger(__name__)


JudgeVerdict = Literal["supported", "partially_supported", "not_supported"]


class JudgeDraft(BaseModel):
    verdict: JudgeVerdict = Field(description="Whether the answer is supported by the supplied evidence.")
    score: int = Field(ge=1, le=5, description="1=fabricated, 3=partial, 5=fully supported with cited claims.")
    reasoning: str = Field(description="One or two sentences explaining the verdict.")


@dataclass
class JudgeResult:
    verdict: JudgeVerdict | None
    score: int | None
    reasoning: str | None
    model: str | None

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "score": self.score,
            "reasoning": self.reasoning,
            "model": self.model,
        }


class GroundednessJudge:
    """LLM-as-judge groundedness scorer.

    When no OpenAI key is configured, judging is skipped gracefully — the eval
    run still completes, just without groundedness numbers.
    """

    def __init__(self) -> None:
        self.client = None
        self.model = settings.openai_answer_model
        if settings.openai_api_key and OpenAI is not None:
            self.client = OpenAI(api_key=settings.openai_api_key)

    @property
    def available(self) -> bool:
        return self.client is not None

    def score(
        self,
        *,
        question: str,
        answer: str,
        retrieved_chunks: list[QueryChunkResult],
    ) -> JudgeResult:
        if self.client is None:
            return JudgeResult(verdict=None, score=None, reasoning="LLM judge not configured.", model=None)

        evidence = "\n\n---\n\n".join(
            f"[{chunk.chunk_id}] {chunk.document_title} pages {chunk.page_start}-{chunk.page_end}\n{chunk.text}"
            for chunk in retrieved_chunks
        ) or "(no evidence)"

        prompt = (
            f"Question:\n{question}\n\n"
            f"Answer to evaluate:\n{answer}\n\n"
            f"Retrieved evidence:\n{evidence}\n\n"
            "Decide whether the answer is supported by the evidence above. Score 1 (fabricated) "
            "to 5 (every substantive claim is supported). Reasoning must be one or two short sentences."
        )

        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=(
                    "You are a strict groundedness judge for a healthcare policy retrieval system. "
                    "Be conservative: penalize unsupported or paraphrased claims, ignore stylistic differences."
                ),
                input=prompt,
                text_format=JudgeDraft,
                max_output_tokens=300,
                temperature=0.0,
                store=False,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("Judge returned no parsed output")
            return JudgeResult(
                verdict=parsed.verdict,
                score=parsed.score,
                reasoning=parsed.reasoning,
                model=self.model,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Groundedness judge call failed: %s", exc)
            return JudgeResult(verdict=None, score=None, reasoning=f"judge_error: {exc}", model=self.model)
