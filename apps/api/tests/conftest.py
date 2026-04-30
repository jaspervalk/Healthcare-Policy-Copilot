import pytest


class _FakeQdrantClient:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def get_collection(self, *_args, **_kwargs):
        raise Exception("no collection")

    def create_collection(self, *_args, **_kwargs) -> None:
        return None

    def create_payload_index(self, *_args, **_kwargs) -> None:
        return None

    def upsert(self, *_args, **_kwargs) -> None:
        return None

    def delete(self, *_args, **_kwargs) -> None:
        return None

    def query_points(self, *_args, **_kwargs):
        class _Result:
            points: list = []

        return _Result()

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _isolate_qdrant_client(monkeypatch):
    """Prevent tests from grabbing the real embedded Qdrant lockfile.

    Replaces the singleton-builder so QdrantIndexService gets a fake client.
    Also resets any cached singleton between tests.
    """
    import app.services.qdrant_index as qdrant_index

    monkeypatch.setattr(qdrant_index, "_build_client", lambda: _FakeQdrantClient())
    monkeypatch.setattr(qdrant_index, "_client", None, raising=False)
    yield
    monkeypatch.setattr(qdrant_index, "_client", None, raising=False)
