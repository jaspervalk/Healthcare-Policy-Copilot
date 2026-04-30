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
    model: str
    dimensions: int
    vectors: list[list[float]]


class EmbeddingError(RuntimeError):
    """Raised when the configured embedding provider fails.

    Deliberately not caught inside the service — silent fallback can poison a
    collection with vectors from a different provider.
    """


class LocalHashingEmbedder:
    provider = "local-hash"
    model = "md5-bucket"

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def embed_many(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            provider=self.provider,
            model=self.model,
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

    @property
    def configured_provider(self) -> str:
        return "openai" if self.client is not None else self.local_embedder.provider

    @property
    def configured_model(self) -> str:
        return settings.openai_embedding_model if self.client is not None else self.local_embedder.model

    def embed_many(self, texts: list[str]) -> EmbeddingBatch:
        if not texts:
            return EmbeddingBatch(
                provider=self.configured_provider,
                model=self.configured_model,
                dimensions=0,
                vectors=[],
            )

        if self.client is None:
            return self.local_embedder.embed_many(texts)

        # Strict path: with OpenAI configured, refuse to silently fall back.
        # Mid-corpus provider switching produces collections with mixed vectors
        # that look fine and retrieve garbage.
        try:
            request: dict[str, object] = {
                "model": settings.openai_embedding_model,
                "input": texts,
            }
            if settings.openai_embedding_model.startswith("text-embedding-3"):
                request["dimensions"] = settings.openai_embedding_dimensions

            response = self.client.embeddings.create(**request)
        except Exception as exc:
            raise EmbeddingError(
                f"OpenAI embedding call failed for model {settings.openai_embedding_model}: {exc}"
            ) from exc

        return EmbeddingBatch(
            provider="openai",
            model=settings.openai_embedding_model,
            dimensions=len(response.data[0].embedding),
            vectors=[item.embedding for item in response.data],
        )

    def embed_query(self, text: str) -> EmbeddingBatch:
        return self.embed_many([text])
