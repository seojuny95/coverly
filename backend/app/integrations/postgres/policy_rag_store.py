"""Storage boundary for uploaded-policy vectors."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from functools import lru_cache

import psycopg
from psycopg import sql

from app.core.config import get_settings
from app.rag.policy.models import PolicyChunk, PolicyRetrievalHit, PolicyVectorRecord

_TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
POLICY_RAG_TABLE_NAME = "policy_rag_chunks"


class PgVectorPolicyStore:
    """Small psycopg adapter for session-scoped vector operations."""

    def __init__(self, database_url: str, *, table_name: str) -> None:
        if not _TABLE_NAME_RE.fullmatch(table_name):
            raise ValueError("policy RAG table name must be a safe SQL identifier")
        self._database_url = database_url
        self._table_name = table_name

    def add(self, records: Sequence[PolicyVectorRecord]) -> None:
        if not records:
            return
        statement = sql.SQL(
            """INSERT INTO {} (
                id, session_id, chunk_index, content_type, content, embedding,
                table_index, created_at, expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s)"""
        ).format(sql.Identifier(self._table_name))
        values = [
            (
                record.chunk.id,
                record.chunk.session_id,
                record.chunk.chunk_index,
                record.chunk.content_type,
                record.chunk.text,
                _vector_literal(record.embedding),
                record.chunk.table_index,
                record.chunk.created_at,
                record.chunk.expires_at,
            )
            for record in records
        ]
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.executemany(statement, values)

    def query(
        self,
        session_ids: Sequence[str],
        query_embedding: tuple[float, ...],
        *,
        top_k: int,
    ) -> list[PolicyRetrievalHit]:
        if not session_ids or top_k <= 0:
            return []
        statement = sql.SQL(
            """SELECT id, session_id, content, content_type, chunk_index,
                      table_index, created_at, expires_at,
                      1 - (embedding <=> %s::vector) AS score
               FROM {}
               WHERE session_id = ANY(%s) AND expires_at > now()
               ORDER BY embedding <=> %s::vector, id
               LIMIT %s"""
        ).format(sql.Identifier(self._table_name))
        vector = _vector_literal(query_embedding)
        with (
            psycopg.connect(self._database_url) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(statement, (vector, list(dict.fromkeys(session_ids)), vector, top_k))
            rows = cursor.fetchall()

        return [
            PolicyRetrievalHit(
                chunk=PolicyChunk(
                    id=str(row[0]),
                    session_id=str(row[1]),
                    text=str(row[2]),
                    content_type=row[3],
                    chunk_index=int(row[4]),
                    table_index=int(row[5]) if row[5] is not None else None,
                    created_at=row[6],
                    expires_at=row[7],
                ),
                score=float(row[8]),
            )
            for row in rows
        ]

    def delete(self, session_id: str) -> None:
        statement = sql.SQL("DELETE FROM {} WHERE session_id = %s").format(
            sql.Identifier(self._table_name)
        )
        with psycopg.connect(self._database_url) as connection:
            connection.execute(statement, (session_id,))

    def delete_expired(self, now: datetime) -> int:
        statement = sql.SQL("DELETE FROM {} WHERE expires_at <= %s").format(
            sql.Identifier(self._table_name)
        )
        with psycopg.connect(self._database_url) as connection:
            cursor = connection.execute(statement, (now,))
            return cursor.rowcount

    def extend(self, session_id: str, expires_at: datetime) -> bool:
        statement = sql.SQL(
            """UPDATE {}
               SET expires_at = %s
               WHERE session_id = %s AND expires_at > now()"""
        ).format(sql.Identifier(self._table_name))
        with psycopg.connect(self._database_url) as connection:
            cursor = connection.execute(statement, (expires_at, session_id))
            return cursor.rowcount > 0


@lru_cache(maxsize=1)
def shared_policy_store() -> PgVectorPolicyStore:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for policy RAG")
    return PgVectorPolicyStore(
        settings.database_url,
        table_name=POLICY_RAG_TABLE_NAME,
    )


def _vector_literal(values: tuple[float, ...]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"
