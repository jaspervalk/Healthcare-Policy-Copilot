from __future__ import annotations

import hashlib
import logging
import math
import re
from dataclasses import dataclass

from app.core.config import settings

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


logger = logging.getLogger(__name__)


@dataclass
class EmbeddingBatch:
    provider: str
    dimensions: int
    vectors: list[list[float]]


class LocalHashingEmbedder:
    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def embed_many(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            provider="local-hash",
            dimensions=self.dimensions,
            vectors=[self._embed(text) for text in texts],
        )

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"\b\w+\b", text.lower())
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class EmbeddingService:
    def __init__(self) -> None:
        self.local_embedder = LocalHashingEmbedder(settings.local_embedding_dimensions)
        self.client = None
        if settings.openai_api_key and OpenAI is not None:
            self.client = OpenAI(api_key=settings.openai_api_key)

    def embed_many(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(provider="none", dimensions=0, vectors=[])

        if self.client is None:
            return self.local_embedder.embed_many(texts)

        try:
            request: dict[str, object] = {
                "model": settings.openai_embedding_model,
                "input": texts,
            }
            if settings.openai_embedding_model.startswith("text-embedding-3"):
                request["dimensions"] = settings.openai_embedding_dimensions

            response = self.client.embeddings.create(**request)
            return EmbeddingBatch(
                provider=f"openai:{settings.openai_embedding_model}",
                dimensions=len(response.data[0].embedding),
                vectors=[item.embedding for item in response.data],
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("OpenAI embeddings failed, falling back to local embedder: %s", exc)
            return self.local_embedder.embed_many(texts)

    def embed_query(self, text: str) -> EmbeddingBatch:
        return self.embed_many([text])

