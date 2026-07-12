"""Supabase pgvector storage for official-source RAG chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from app.services.llm import Embedder, embed_texts
from app.services.rag.chunking import RagChunk

_TABLE = "official_rag_chunks"
_MAX_EMBEDDING_TEXT_CHARS = 6_000


@dataclass(frozen=True)
class VectorChunkHit:
    chunk: RagChunk
    score: float


def ensure_schema(database_url: str, *, dimensions: int) -> None:
    with _connect(database_url) as conn:
        _ensure_schema(conn, dimensions=dimensions)


def index_chunks(
    database_url: str,
    chunks: tuple[RagChunk, ...],
    *,
    dimensions: int,
    embed: Embedder = embed_texts,
    batch_size: int = 64,
) -> int:
    """Create/update the official RAG vector index."""
    if not chunks:
        return 0
    with _connect(database_url) as conn:
        _ensure_schema(conn, dimensions=dimensions)
        indexed = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            embeddings = embed([_embedding_text(chunk) for chunk in batch])
            if len(embeddings) != len(batch):
                raise RuntimeError("embedding count mismatch")
            for chunk, embedding in zip(batch, embeddings, strict=True):
                _upsert_chunk(conn, chunk, embedding)
                indexed += 1
        _delete_stale_chunks(conn, tuple(chunk.id for chunk in chunks))
        conn.commit()
    return indexed


def search_chunks(
    database_url: str,
    query: str,
    *,
    final_k: int,
    embed: Embedder = embed_texts,
) -> list[VectorChunkHit]:
    """Search official chunks by pgvector cosine distance."""
    query_embedding = embed([query])[0]
    vector = _vector_literal(query_embedding)
    with _connect(database_url, row_factory=dict_row) as conn:
        rows = conn.execute(
            f"""
            SELECT
              chunk_id, source_id, source_title, source_category, publisher,
              text, page_start, page_end, label, citation_label, version_label,
              source_url, local_path,
              1 - (embedding <=> %s::vector) AS score
            FROM {_TABLE}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector, vector, final_k),
        ).fetchall()
    return [_row_to_hit(row) for row in rows]


def _ensure_schema(conn: Connection[Any], *, dimensions: int) -> None:
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
          chunk_id text PRIMARY KEY,
          source_id text NOT NULL,
          source_title text NOT NULL,
          source_category text NOT NULL,
          publisher text NOT NULL,
          text text NOT NULL,
          page_start integer NOT NULL,
          page_end integer NOT NULL,
          label text,
          citation_label text,
          version_label text,
          source_url text,
          local_path text,
          embedding vector({dimensions}) NOT NULL,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        f"""
        CREATE INDEX IF NOT EXISTS official_rag_chunks_embedding_idx
        ON {_TABLE}
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 32)
        """
    )


def _connect(database_url: str, **kwargs: Any) -> Connection[Any]:
    return psycopg.connect(database_url, **kwargs)


def _delete_stale_chunks(conn: Connection[Any], active_chunk_ids: tuple[str, ...]) -> None:
    if not active_chunk_ids:
        conn.execute(f"DELETE FROM {_TABLE}")
        return
    conn.execute(
        f"DELETE FROM {_TABLE} WHERE NOT (chunk_id = ANY(%s))",
        (list(active_chunk_ids),),
    )


def _upsert_chunk(conn: Connection[Any], chunk: RagChunk, embedding: list[float]) -> None:
    conn.execute(
        f"""
        INSERT INTO {_TABLE} (
          chunk_id, source_id, source_title, source_category, publisher,
          text, page_start, page_end, label, citation_label, version_label,
          source_url, local_path, embedding, updated_at
        )
        VALUES (
          %(chunk_id)s, %(source_id)s, %(source_title)s, %(source_category)s, %(publisher)s,
          %(text)s, %(page_start)s, %(page_end)s, %(label)s, %(citation_label)s,
          %(version_label)s, %(source_url)s, %(local_path)s, %(embedding)s::vector, now()
        )
        ON CONFLICT (chunk_id) DO UPDATE SET
          source_id = EXCLUDED.source_id,
          source_title = EXCLUDED.source_title,
          source_category = EXCLUDED.source_category,
          publisher = EXCLUDED.publisher,
          text = EXCLUDED.text,
          page_start = EXCLUDED.page_start,
          page_end = EXCLUDED.page_end,
          label = EXCLUDED.label,
          citation_label = EXCLUDED.citation_label,
          version_label = EXCLUDED.version_label,
          source_url = EXCLUDED.source_url,
          local_path = EXCLUDED.local_path,
          embedding = EXCLUDED.embedding,
          updated_at = now()
        """,
        {
            "chunk_id": chunk.id,
            "source_id": chunk.source_id,
            "source_title": chunk.source_title,
            "source_category": chunk.source_category,
            "publisher": chunk.publisher,
            "text": chunk.text,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "label": chunk.label,
            "citation_label": chunk.citation_label,
            "version_label": chunk.version_label,
            "source_url": chunk.source_url,
            "local_path": chunk.local_path,
            "embedding": _vector_literal(embedding),
        },
    )


def _row_to_hit(row: dict[str, Any]) -> VectorChunkHit:
    return VectorChunkHit(
        chunk=RagChunk(
            id=str(row["chunk_id"]),
            source_id=str(row["source_id"]),
            source_title=str(row["source_title"]),
            source_category=str(row["source_category"]),
            publisher=str(row["publisher"]),
            text=str(row["text"]),
            page_start=int(row["page_start"]),
            page_end=int(row["page_end"]),
            label=_optional_str(row["label"]),
            citation_label=_optional_str(row["citation_label"]),
            version_label=_optional_str(row["version_label"]),
            source_url=_optional_str(row["source_url"]),
            local_path=_optional_str(row["local_path"]),
        ),
        score=float(row["score"]),
    )


def _embedding_text(chunk: RagChunk) -> str:
    label = chunk.label or chunk.citation_label or chunk.source_title
    text = f"{chunk.source_title}\n{label}\n{chunk.text}"
    if len(text) <= _MAX_EMBEDDING_TEXT_CHARS:
        return text
    return text[: _MAX_EMBEDDING_TEXT_CHARS - 1].rstrip() + "…"


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
