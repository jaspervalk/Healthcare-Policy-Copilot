import pytest

from app.services.embeddings import EmbeddingError, EmbeddingService, LocalHashingEmbedder


class _RaisingEmbeddings:
    def create(self, **_kwargs):
        raise RuntimeError("simulated openai outage")


class _RaisingClient:
    def __init__(self) -> None:
        self.embeddings = _RaisingEmbeddings()


def test_local_embedder_returns_provider_and_model():
    embedder = LocalHashingEmbedder(dimensions=64)

    batch = embedder.embed_many(["hello world"])

    assert batch.provider == "local-hash"
    assert batch.model == "md5-bucket"
    assert batch.dimensions == 64
    assert len(batch.vectors) == 1


def test_embedding_service_falls_back_to_local_only_when_no_openai_client():
    service = EmbeddingService()
    service.client = None

    batch = service.embed_many(["a chunk"])

    assert batch.provider == "local-hash"
    assert batch.model == "md5-bucket"


def test_embedding_service_raises_when_configured_openai_call_fails():
    """With OpenAI configured, failures must propagate — no silent local fallback."""
    service = EmbeddingService()
    service.client = _RaisingClient()

    with pytest.raises(EmbeddingError):
        service.embed_many(["a chunk"])
