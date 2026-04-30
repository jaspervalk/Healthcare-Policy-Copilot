from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[4]
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_name: str = "Healthcare Policy Copilot API"
    api_v1_prefix: str = "/api"
    database_url: str = f"sqlite:///{DATA_DIR / 'app.db'}"
    data_dir: Path = DATA_DIR
    raw_documents_dir: Path = DATA_DIR / "raw"
    processed_documents_dir: Path = DATA_DIR / "processed"
    qdrant_local_path: Path = DATA_DIR / "qdrant"
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "policy_chunks"
    qdrant_timeout_seconds: int = 60
    qdrant_upsert_batch_size: int = 16
    openai_api_key: str | None = None
    openai_answer_model: str = "gpt-5.4-mini"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dimensions: int = 1024
    local_embedding_dimensions: int = 256
    default_query_limit: int = 5
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    max_upload_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    admin_token: str | None = None  # When set, DELETE/PATCH require Bearer auth.

    @property
    def use_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def prepare_runtime_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_documents_dir.mkdir(parents=True, exist_ok=True)
        self.processed_documents_dir.mkdir(parents=True, exist_ok=True)
        self.qdrant_local_path.mkdir(parents=True, exist_ok=True)


settings = Settings()
