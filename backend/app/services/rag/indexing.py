"""Indexing pipeline for official-source RAG.

Read this file first when you want the ingestion flow: load official files,
chunk them, embed each chunk, then save the vector store.
"""

from __future__ import annotations

from app.services.rag.embeddings import Embedder, openai_embedder_from_settings
from app.services.rag.loaders import load_official_chunks
from app.services.rag.models import RagChunk, VectorRecord, chunk_embedding_text
from app.services.rag.pgvector_store import shared_pgvector_store


def build_vector_records(
    *,
    embedder: Embedder | None = None,
    chunks: tuple[RagChunk, ...] | None = None,
) -> tuple[VectorRecord, ...]:
    """Load, chunk, and embed official sources into pgvector-ready records.

    Defaults to the OpenAI embedder so the index matches production retrieval's
    embedding space. Tests and offline diagnostics pass ``HashingEmbedder``
    explicitly instead.
    """

    active_embedder = embedder or openai_embedder_from_settings()
    active_chunks = chunks if chunks is not None else load_official_chunks()
    embeddings = active_embedder.embed_texts(
        [chunk_embedding_text(chunk) for chunk in active_chunks]
    )

    return tuple(
        VectorRecord(chunk=chunk, embedding=embedding)
        for chunk, embedding in zip(active_chunks, embeddings, strict=True)
    )


def index_official_sources(*, embedder: Embedder | None = None) -> int:
    """Build the official-source index and replace the pgvector contents."""

    records = build_vector_records(embedder=embedder)
    shared_pgvector_store().replace_all(records)
    return len(records)


def main() -> None:
    count = index_official_sources()
    print(f"indexed {count} official RAG chunks into pgvector")


if __name__ == "__main__":
    main()
