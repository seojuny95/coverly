from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    database_url: str = ""
    reference_data_database_enabled: bool = True
    rag_pg_table: str = "official_rag_chunks"
    reference_schema: str = "reference"
    premium_benchmark_table: str = "premium_benchmarks"
    reference_source_table: str = "sources"
    policy_change_table: str = "policy_change_notes"
    rag_embedding_dim: int = 1536
    policy_rag_ttl_seconds: int = 15 * 60
    policy_rag_max_ttl_seconds: int = 2 * 60 * 60
    policy_rag_session_secret: str = ""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
