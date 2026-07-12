"""CLI helper to index official RAG sources into Supabase pgvector."""

from app.services.rag.pgvector_store import index_chunks
from app.services.rag.retrieve import load_official_chunks
from app.settings import get_settings


def index_official_rag() -> int:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    chunks = load_official_chunks()
    return index_chunks(
        settings.database_url,
        chunks,
        dimensions=settings.openai_embedding_dimensions,
    )


if __name__ == "__main__":
    count = index_official_rag()
    print(f"indexed {count} official RAG chunks")
