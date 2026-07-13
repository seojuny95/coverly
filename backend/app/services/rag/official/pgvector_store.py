"""pgvector storage boundary for official-source RAG."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from llama_index.core.schema import BaseNode, MetadataMode, TextNode
from llama_index.core.vector_stores import VectorStoreQuery
from llama_index.core.vector_stores.types import VectorStoreQueryMode
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import text

from app.services.rag.official.models import RagChunk, RetrievalHit, VectorRecord
from app.settings import get_settings


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

        engine = self._vector_store.client
        with engine.begin() as connection:
            connection.execute(text(f'DROP TABLE IF EXISTS "{backup_table}"'))
            connection.execute(
                text(f'ALTER TABLE IF EXISTS "{live_table}" RENAME TO "{backup_table}"')
            )
            connection.execute(text(f'ALTER TABLE "{staging_table}" RENAME TO "{live_table}"'))
            connection.execute(text(f'DROP TABLE IF EXISTS "{backup_table}"'))

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
