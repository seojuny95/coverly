"""pgvector storage boundary for official-source RAG."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from llama_index.core.schema import BaseNode, MetadataMode, TextNode
from llama_index.core.vector_stores import VectorStoreQuery
from llama_index.core.vector_stores.types import VectorStoreQueryMode
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.rag.official.models import (
    RagChunk,
    RetrievalHit,
    VectorRecord,
)


class PgVectorRagStore:
    """Thin adapter from Coverly chunks to LlamaIndex PGVectorStore nodes."""

    def __init__(
        self,
        vector_store: PGVectorStore,
        *,
        embedding_model: str,
        database_url: str,
        table_name: str,
        embed_dim: int,
    ) -> None:
        self._vector_store = vector_store
        self.embedding_model = embedding_model
        self._database_url = database_url
        self._table_name = table_name
        self._embed_dim = embed_dim

    @classmethod
    def from_settings(cls) -> PgVectorRagStore:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured")

        return cls(
            _pg_vector_store_from_database_url(
                settings.database_url,
                table_name=settings.rag_pg_table,
                embed_dim=settings.rag_embedding_dim,
            ),
            embedding_model=settings.openai_embedding_model,
            database_url=settings.database_url,
            table_name=settings.rag_pg_table,
            embed_dim=settings.rag_embedding_dim,
        )

    def replace_all(self, records: tuple[VectorRecord, ...]) -> None:
        """Replace the official-source index contents with the given records.

        Builds the new index in a staging table first and only swaps it into
        the serving table name once every record has been written. If the
        embedder or database has a transient failure mid-write, the currently
        serving index is untouched instead of being left cleared.
        """

        staging_table_name = f"{self._table_name}_staging"
        self._drop_table_if_exists(staging_table_name)
        self._drop_table_if_exists(f"{self._table_name}_old")
        self._drop_index_if_exists(f"data_{staging_table_name}_embedding_idx")
        self._drop_constraint_if_exists(
            f"data_{self._table_name}",
            f"data_{staging_table_name}_pkey",
        )
        self._drop_index_if_exists(f"{staging_table_name}_idx")
        self._drop_index_if_exists(f"{staging_table_name}_idx_1")
        staging_store = _pg_vector_store_from_database_url(
            self._database_url,
            table_name=staging_table_name,
            embed_dim=self._embed_dim,
        )
        staging_store.clear()
        if records:
            staging_store.add([_node_from_record(record) for record in records])

        self._swap_in_staging_table(staging_table_name)

    def _swap_in_staging_table(self, staging_table_name: str) -> None:
        live_table = f"data_{self._table_name}"
        staging_table = f"data_{staging_table_name}"
        backup_table = f"{live_table}_old"

        engine = create_engine(self._database_url)
        with engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS "{backup_table}"'))
            connection.execute(
                text(f'ALTER TABLE IF EXISTS "{live_table}" RENAME TO "{backup_table}"')
            )
            connection.execute(text(f'ALTER TABLE "{staging_table}" RENAME TO "{live_table}"'))
            connection.execute(text(f'DROP TABLE IF EXISTS "{backup_table}"'))
            self._normalize_live_index_names(connection, staging_table_name)
        engine.dispose()

    def _normalize_live_index_names(self, connection: Connection, staging_table_name: str) -> None:
        live_table = f"data_{self._table_name}"
        staging_table = f"data_{staging_table_name}"
        staging_pkey = f"data_{staging_table_name}_pkey"
        if self._constraint_exists(connection, table_name=live_table, constraint_name=staging_pkey):
            connection.execute(
                text(
                    f'ALTER TABLE IF EXISTS "{live_table}" '
                    f'RENAME CONSTRAINT "{staging_pkey}" '
                    f'TO "{live_table}_pkey"'
                )
            )
        statements = (
            (
                f'ALTER INDEX IF EXISTS "{staging_table}_embedding_idx" '
                f'RENAME TO "{live_table}_embedding_idx"'
            ),
            (
                f'ALTER INDEX IF EXISTS "{staging_table_name}_idx" '
                f'RENAME TO "{live_table}_text_search_tsv_idx"'
            ),
            (
                f'ALTER INDEX IF EXISTS "{staging_table_name}_idx_1" '
                f'RENAME TO "{live_table}_ref_doc_id_idx"'
            ),
        )
        for statement in statements:
            connection.execute(text(statement))

    def _constraint_exists(
        self,
        connection: Connection,
        *,
        table_name: str,
        constraint_name: str,
    ) -> bool:
        result = connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = to_regclass(:table_name)
                      AND conname = :constraint_name
                )
                """
            ),
            {"table_name": f"public.{table_name}", "constraint_name": constraint_name},
        )
        return bool(result.scalar())

    def _drop_table_if_exists(self, table_name: str) -> None:
        engine = create_engine(self._database_url)
        with engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS "data_{table_name}" CASCADE'))
        engine.dispose()

    def _drop_index_if_exists(self, index_name: str) -> None:
        engine = create_engine(self._database_url)
        with engine.begin() as connection:
            connection.execute(text(f'DROP INDEX IF EXISTS "{index_name}"'))
        engine.dispose()

    def _drop_constraint_if_exists(self, table_name: str, constraint_name: str) -> None:
        engine = create_engine(self._database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    f'ALTER TABLE IF EXISTS "{table_name}" '
                    f'DROP CONSTRAINT IF EXISTS "{constraint_name}"'
                )
            )
        engine.dispose()

    def query(
        self,
        *,
        query_embedding: tuple[float, ...],
        query_text: str,
        top_k: int,
    ) -> list[RetrievalHit]:
        result = self._vector_store.query(
            VectorStoreQuery(
                query_embedding=list(query_embedding),
                query_str=query_text,
                similarity_top_k=top_k,
                mode=VectorStoreQueryMode.HYBRID,
                hybrid_top_k=top_k,
            )
        )
        nodes = result.nodes or []
        similarities = result.similarities or []

        hits: list[RetrievalHit] = []
        for index, node in enumerate(nodes):
            score = float(similarities[index]) if index < len(similarities) else 0.0
            hits.append(
                RetrievalHit(
                    chunk=_chunk_from_node(node),
                    score=score,
                    keyword_score=0.0,
                    vector_score=score,
                )
            )

        return hits


@lru_cache(maxsize=1)
def shared_pgvector_store() -> PgVectorRagStore:
    """Return a process-wide store so requests reuse one connection pool."""

    return PgVectorRagStore.from_settings()


def _pg_vector_store_from_database_url(
    database_url: str,
    *,
    table_name: str,
    embed_dim: int,
) -> PGVectorStore:
    parsed = urlparse(database_url)
    database = parsed.path.lstrip("/")
    if not database:
        raise RuntimeError("DATABASE_URL must include a database name")

    return PGVectorStore.from_params(
        database=database,
        host=parsed.hostname,
        password=parsed.password,
        port=str(parsed.port or 5432),
        user=parsed.username,
        table_name=table_name,
        embed_dim=embed_dim,
        hybrid_search=True,
        text_search_config="simple",
        perform_setup=True,
        use_jsonb=True,
        hnsw_kwargs={
            "hnsw_m": 16,
            "hnsw_ef_construction": 64,
            "hnsw_ef_search": 40,
            "hnsw_dist_method": "vector_cosine_ops",
        },
    )


def _node_from_record(record: VectorRecord) -> TextNode:
    chunk = record.chunk
    return TextNode(
        id_=chunk.id,
        text=chunk.text,
        embedding=list(record.embedding),
        metadata={
            "source_id": chunk.source_id,
            "source_title": chunk.source_title,
            "source_category": chunk.source_category,
            "publisher": chunk.publisher,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "label": chunk.label,
            "citation_label": chunk.citation_label,
            "version_label": chunk.version_label,
            "source_url": chunk.source_url,
            "local_path": chunk.local_path,
        },
    )


def _chunk_from_node(node: BaseNode) -> RagChunk:
    metadata = node.metadata
    return RagChunk(
        id=node.node_id,
        source_id=str(metadata.get("source_id") or ""),
        source_title=str(metadata.get("source_title") or ""),
        source_category=str(metadata.get("source_category") or ""),
        publisher=str(metadata.get("publisher") or ""),
        text=node.get_content(metadata_mode=MetadataMode.NONE),
        page_start=int(metadata.get("page_start") or 0),
        page_end=int(metadata.get("page_end") or 0),
        label=_optional_str(metadata.get("label")),
        citation_label=_optional_str(metadata.get("citation_label")),
        version_label=_optional_str(metadata.get("version_label")),
        source_url=_optional_str(metadata.get("source_url")),
        local_path=_optional_str(metadata.get("local_path")),
    )


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
