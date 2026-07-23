from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.limits import MAX_PORTFOLIO_DOCUMENTS

DEFAULT_BACKEND_CORS_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


class Settings(BaseSettings):
    # Secrets are SecretStr so that a repr of Settings -- e.g. a failing
    # assertion message -- can never dump live credentials into CI logs.
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    database_url: SecretStr = SecretStr("")
    reference_data_database_enabled: bool = True
    rag_pg_table: str = "official_rag_chunks"
    reference_schema: str = "reference"
    premium_burden_guide_table: str = "premium_burden_guides"
    reference_source_table: str = "sources"
    rag_embedding_dim: int = 1536
    policy_rag_ttl_seconds: int = 15 * 60
    policy_rag_max_ttl_seconds: int = 2 * 60 * 60
    policy_rag_session_secret: SecretStr = SecretStr("")
    portfolio_session_max_documents: int = Field(
        default=MAX_PORTFOLIO_DOCUMENTS,
        ge=MAX_PORTFOLIO_DOCUMENTS,
        le=MAX_PORTFOLIO_DOCUMENTS,
    )
    pdf_parsing_max_concurrency: int = Field(default=2, ge=1, le=32)
    pdf_parsing_max_queue_size: int = Field(default=8, ge=0, le=128)
    pdf_parsing_queue_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    pdf_parsing_retry_after_seconds: int = Field(default=5, ge=1, le=300)
    counsel_max_turns_per_session: int = 10
    counsel_agent_max_turns: int = 10
    counsel_history_turns: int = 5
    policy_upload_reservation_ttl_seconds: int = 15 * 60
    backend_cors_origins: str = ",".join(DEFAULT_BACKEND_CORS_ORIGINS)

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def parsed_backend_cors_origins(self) -> list[str]:
        return [
            origin
            for raw_origin in self.backend_cors_origins.split(",")
            if (origin := raw_origin.strip())
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
