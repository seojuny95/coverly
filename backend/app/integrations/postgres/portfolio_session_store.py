"""Postgres persistence for short-lived portfolio sessions."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    NewPortfolioSession,
    PortfolioSessionSnapshot,
    StoredPolicyDocument,
)
from app.modules.portfolio.session.repository import (
    AddDocumentResult,
    PortfolioPolicySelectionNotFound,
)


class PgPortfolioSessionRepository:
    def __init__(self, database_url: str) -> None:
        self._pool = ConnectionPool[Connection[dict[str, Any]]](
            database_url,
            min_size=0,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )

    def close(self) -> None:
        self._pool.close()

    def create(self, session: NewPortfolioSession) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                "DELETE FROM private.portfolio_sessions WHERE max_expires_at <= now()"
            )
            connection.execute(
                """INSERT INTO private.portfolio_sessions (
                       id, created_at, expires_at, max_expires_at
                   ) VALUES (%s, %s, %s, %s)""",
                (
                    session.id,
                    session.created_at,
                    session.expires_at,
                    session.max_expires_at,
                ),
            )

    def add_document(
        self,
        session_id: str,
        document: StoredPolicyDocument,
        *,
        now: datetime,
        max_documents: int,
    ) -> AddDocumentResult:
        payload = document.policy.model_dump(mode="json", exclude_none=True)
        with self._pool.connection() as connection:
            session = connection.execute(
                """SELECT id FROM private.portfolio_sessions
                   WHERE id = %s AND expires_at > %s
                   FOR UPDATE""",
                (session_id, now),
            ).fetchone()
            if session is None:
                return "missing"
            cancelled = connection.execute(
                """SELECT 1 FROM private.policy_document_tombstones
                   WHERE portfolio_session_id = %s AND document_id = %s""",
                (session_id, document.id),
            ).fetchone()
            if cancelled is not None:
                return "cancelled"
            document_count = connection.execute(
                """SELECT count(*) FROM private.policy_documents
                   WHERE portfolio_session_id = %s""",
                (session_id,),
            ).fetchone()
            if document_count is not None and int(document_count["count"]) >= max_documents:
                return "limit_exceeded"
            connection.execute(
                """INSERT INTO private.policy_documents (
                       id, portfolio_session_id, structured_policy, rag_session_id
                   ) VALUES (%s, %s, %s::jsonb, %s)""",
                (
                    document.id,
                    session_id,
                    json.dumps(payload, ensure_ascii=False),
                    document.rag_session_id,
                ),
            )
            connection.execute(
                """UPDATE private.portfolio_sessions
                   SET version = version + 1,
                       analysis_context_hash = null,
                       analysis_version = null,
                       analysis_result = null
                   WHERE id = %s""",
                (session_id,),
            )
        return "stored"

    def snapshot(
        self,
        session_id: str,
        *,
        policy_ids: tuple[str, ...] | None,
        now: datetime,
    ) -> PortfolioSessionSnapshot | None:
        with self._pool.connection() as connection:
            session = connection.execute(
                """SELECT version FROM private.portfolio_sessions
                   WHERE id = %s AND expires_at > %s""",
                (session_id, now),
            ).fetchone()
            if session is None:
                return None
            params: list[object] = [session_id]
            selection = ""
            if policy_ids is not None:
                selection = " AND id = ANY(%s)"
                params.append(list(policy_ids))
            rows = connection.execute(
                """SELECT id, structured_policy, rag_session_id
                   FROM private.policy_documents
                   WHERE portfolio_session_id = %s"""
                + selection
                + " ORDER BY created_at, id",
                params,
            ).fetchall()
            if policy_ids is not None and len(rows) != len(policy_ids):
                raise PortfolioPolicySelectionNotFound

        policies = tuple(PolicyInput.model_validate(row["structured_policy"]) for row in rows)
        rag_session_ids = tuple(
            str(row["rag_session_id"]) for row in rows if row["rag_session_id"] is not None
        )
        return PortfolioSessionSnapshot(
            session_id=session_id,
            version=int(session["version"]),
            policies=policies,
            rag_session_ids=rag_session_ids,
        )

    def extend(
        self,
        session_id: str,
        expires_at: datetime,
        *,
        now: datetime,
    ) -> tuple[str, ...] | None:
        with self._pool.connection() as connection:
            updated = connection.execute(
                """UPDATE private.portfolio_sessions
                   SET expires_at = %s
                   WHERE id = %s AND expires_at > %s
                   RETURNING id""",
                (expires_at, session_id, now),
            ).fetchone()
            if updated is None:
                return None
            rows = connection.execute(
                """SELECT rag_session_id FROM private.policy_documents
                   WHERE portfolio_session_id = %s AND rag_session_id IS NOT NULL""",
                (session_id,),
            ).fetchall()
        return tuple(str(row["rag_session_id"]) for row in rows)

    def delete(self, session_id: str) -> tuple[str, ...] | None:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """SELECT rag_session_id FROM private.policy_documents
                   WHERE portfolio_session_id = %s AND rag_session_id IS NOT NULL""",
                (session_id,),
            ).fetchall()
            deleted = connection.execute(
                "DELETE FROM private.portfolio_sessions WHERE id = %s RETURNING id",
                (session_id,),
            ).fetchone()
        if deleted is None:
            return None
        return tuple(str(row["rag_session_id"]) for row in rows)

    def delete_documents(
        self,
        session_id: str,
        document_ids: tuple[str, ...],
        *,
        now: datetime,
    ) -> tuple[str, ...] | None:
        with self._pool.connection() as connection:
            session = connection.execute(
                """SELECT id FROM private.portfolio_sessions
                   WHERE id = %s AND expires_at > %s
                   FOR UPDATE""",
                (session_id, now),
            ).fetchone()
            if session is None:
                return None
            connection.execute(
                """INSERT INTO private.policy_document_tombstones (
                       portfolio_session_id, document_id
                   )
                   SELECT %s, requested.document_id
                   FROM unnest(%s::uuid[]) AS requested(document_id)
                   ON CONFLICT DO NOTHING""",
                (session_id, list(document_ids)),
            )
            rows = connection.execute(
                """DELETE FROM private.policy_documents
                   WHERE portfolio_session_id = %s AND id = ANY(%s)
                   RETURNING rag_session_id""",
                (session_id, list(document_ids)),
            ).fetchall()
            if rows:
                connection.execute(
                    """UPDATE private.portfolio_sessions
                       SET version = version + 1,
                           analysis_context_hash = null,
                           analysis_version = null,
                           analysis_result = null
                       WHERE id = %s""",
                    (session_id,),
                )
        return tuple(
            str(row["rag_session_id"]) for row in rows if row["rag_session_id"] is not None
        )

    def load_cached_analysis(
        self,
        session_id: str,
        *,
        version: int,
        context_hash: str,
    ) -> CachedPortfolioAnalysis | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """SELECT analysis_version, analysis_context_hash, analysis_result
                   FROM private.portfolio_sessions
                   WHERE id = %s AND analysis_version = %s
                     AND analysis_context_hash = %s AND analysis_result IS NOT NULL""",
                (session_id, version, context_hash),
            ).fetchone()
        if row is None:
            return None
        return CachedPortfolioAnalysis(
            version=int(row["analysis_version"]),
            context_hash=str(row["analysis_context_hash"]),
            result=dict(row["analysis_result"]),
        )

    def save_cached_analysis(
        self,
        session_id: str,
        analysis: CachedPortfolioAnalysis,
    ) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """UPDATE private.portfolio_sessions
                   SET analysis_version = %s,
                       analysis_context_hash = %s,
                       analysis_result = %s::jsonb
                   WHERE id = %s AND version = %s""",
                (
                    analysis.version,
                    analysis.context_hash,
                    json.dumps(analysis.result, ensure_ascii=False),
                    session_id,
                    analysis.version,
                ),
            )
