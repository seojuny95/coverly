from typing import Any, cast

import pytest
from pytest import raises
from sqlalchemy.engine import Connection

from app.integrations.postgres import official_rag_store as pgvector_store_module
from app.integrations.postgres.official_rag_store import (
    PgVectorRagStore,
    _chunk_from_node,
    _node_from_record,
)
from app.rag.official.models import RagChunk, VectorRecord


def test_pgvector_node_round_trip_keeps_chunk_metadata() -> None:
    chunk = RagChunk(
        id="chunk-1",
        source_id="standard_terms_annex_15_2026_06_30",
        source_title="표준약관",
        source_category="standard_clause",
        publisher="금융감독원",
        text="계약 전 알릴 의무",
        page_start=1,
        page_end=2,
        label="제1조",
        citation_label="표준약관 제1조",
        version_label="시행일 2026-06-30",
        source_url="https://example.test/source.pdf",
        local_path="/tmp/source.pdf",
    )

    node = _node_from_record(VectorRecord(chunk=chunk, embedding=(0.1, 0.2)))
    restored = _chunk_from_node(node)

    assert restored == chunk


def test_pgvector_node_requires_real_database_name() -> None:
    from app.integrations.postgres.official_rag_store import _pg_vector_store_from_database_url

    with raises(RuntimeError, match="database name"):
        _pg_vector_store_from_database_url(
            "postgresql://postgres:password@localhost:5432",
            table_name="official_rag_chunks",
            embed_dim=1536,
        )


def test_shared_pgvector_store_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: retrieval used to build a fresh PGVectorStore (and its
    connection pool) on every request instead of reusing one per process."""

    calls = {"count": 0}

    class _StubStore:
        pass

    def _fake_from_settings(cls: type[PgVectorRagStore]) -> _StubStore:
        calls["count"] += 1
        return _StubStore()

    monkeypatch.setattr(PgVectorRagStore, "from_settings", classmethod(_fake_from_settings))
    pgvector_store_module.shared_pgvector_store.cache_clear()
    try:
        first = pgvector_store_module.shared_pgvector_store()
        second = pgvector_store_module.shared_pgvector_store()

        assert first is second
        assert calls["count"] == 1
    finally:
        pgvector_store_module.shared_pgvector_store.cache_clear()


def test_normalize_live_index_names_skips_missing_staging_pkey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = PgVectorRagStore.__new__(PgVectorRagStore)
    store._table_name = "official_rag_chunks"
    statements: list[str] = []

    class _FakeConnection:
        def execute(self, statement: Any, *args: object, **kwargs: object) -> None:
            statements.append(str(statement))

    monkeypatch.setattr(store, "_constraint_exists", lambda *args, **kwargs: False)

    store._normalize_live_index_names(
        cast(Connection, _FakeConnection()),
        "official_rag_chunks_staging",
    )

    assert all("RENAME CONSTRAINT" not in statement for statement in statements)
    assert len(statements) == 3


def test_normalize_live_index_names_renames_existing_staging_pkey(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = PgVectorRagStore.__new__(PgVectorRagStore)
    store._table_name = "official_rag_chunks"
    statements: list[str] = []

    class _FakeConnection:
        def execute(self, statement: Any, *args: object, **kwargs: object) -> None:
            statements.append(str(statement))

    monkeypatch.setattr(store, "_constraint_exists", lambda *args, **kwargs: True)

    store._normalize_live_index_names(
        cast(Connection, _FakeConnection()),
        "official_rag_chunks_staging",
    )

    assert any("RENAME CONSTRAINT" in statement for statement in statements)
    assert len(statements) == 4
