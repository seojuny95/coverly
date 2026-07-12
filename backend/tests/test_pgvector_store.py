from typing import Any

from pytest import MonkeyPatch

from app.services.rag import pgvector_store
from app.services.rag.chunking import RagChunk


class _FakeRowsConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def __enter__(self) -> "_FakeRowsConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object | None = None) -> "_FakeRowsConnection":
        self.sql.append(sql)
        return self

    def fetchall(self) -> list[dict[str, Any]]:
        return []


class _FakeWriteConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.committed = False

    def __enter__(self) -> "_FakeWriteConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object | None = None) -> None:
        self.sql.append(sql)

    def commit(self) -> None:
        self.committed = True


def _chunk(chunk_id: str) -> RagChunk:
    return RagChunk(
        id=chunk_id,
        source_id="standard_terms_annex_15_2026_06_30",
        source_title="표준약관",
        source_category="standard_clause",
        publisher="금융감독원",
        text="계약 전 알릴 의무",
        page_start=1,
        page_end=1,
        label="제1조",
    )


def test_search_chunks_does_not_run_schema_ddl(monkeypatch: MonkeyPatch) -> None:
    conn = _FakeRowsConnection()
    monkeypatch.setattr(pgvector_store, "_connect", lambda *_args, **_kwargs: conn)

    pgvector_store.search_chunks(
        "postgresql://example",
        "계약 전 알릴 의무",
        final_k=3,
        embed=lambda _texts: [[0.1, 0.2]],
    )

    rendered_sql = "\n".join(conn.sql)
    assert "CREATE TABLE" not in rendered_sql
    assert "CREATE INDEX" not in rendered_sql
    assert "SELECT" in rendered_sql


def test_ensure_schema_creates_vector_table_and_index(monkeypatch: MonkeyPatch) -> None:
    conn = _FakeWriteConnection()
    monkeypatch.setattr(pgvector_store, "_connect", lambda *_args, **_kwargs: conn)

    pgvector_store.ensure_schema("postgresql://example", dimensions=2)

    rendered_sql = "\n".join(conn.sql)
    assert "CREATE TABLE IF NOT EXISTS official_rag_chunks" in rendered_sql
    assert "CREATE INDEX IF NOT EXISTS official_rag_chunks_embedding_idx" in rendered_sql


def test_index_chunks_prunes_stale_chunks(monkeypatch: MonkeyPatch) -> None:
    conn = _FakeWriteConnection()
    monkeypatch.setattr(pgvector_store, "_connect", lambda *_args, **_kwargs: conn)

    indexed = pgvector_store.index_chunks(
        "postgresql://example",
        (_chunk("active-1"),),
        dimensions=2,
        embed=lambda _texts: [[0.1, 0.2]],
    )

    assert indexed == 1
    assert conn.committed is True
    assert any("DELETE FROM official_rag_chunks" in sql for sql in conn.sql)
