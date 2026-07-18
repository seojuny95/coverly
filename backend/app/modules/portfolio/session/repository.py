"""Persistence protocol for portfolio sessions."""

from datetime import datetime
from typing import Literal, Protocol

from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    NewPortfolioSession,
    PortfolioSessionSnapshot,
    StoredPolicyDocument,
)

AddDocumentResult = Literal["stored", "missing", "limit_exceeded", "cancelled"]


class PortfolioPolicySelectionNotFound(Exception):
    """One or more requested policy documents do not belong to the session."""


class PortfolioSessionRepository(Protocol):
    def create(self, session: NewPortfolioSession) -> None: ...

    def add_document(
        self,
        session_id: str,
        document: StoredPolicyDocument,
        *,
        now: datetime,
        max_documents: int,
    ) -> AddDocumentResult: ...

    def snapshot(
        self,
        session_id: str,
        *,
        policy_ids: tuple[str, ...] | None,
        now: datetime,
    ) -> PortfolioSessionSnapshot | None: ...

    def extend(
        self,
        session_id: str,
        expires_at: datetime,
        *,
        now: datetime,
    ) -> tuple[str, ...] | None: ...

    def delete(self, session_id: str) -> tuple[str, ...] | None: ...

    def delete_documents(
        self,
        session_id: str,
        document_ids: tuple[str, ...],
        *,
        now: datetime,
    ) -> tuple[str, ...] | None: ...

    def load_cached_analysis(
        self,
        session_id: str,
        *,
        version: int,
        context_hash: str,
    ) -> CachedPortfolioAnalysis | None: ...

    def save_cached_analysis(
        self,
        session_id: str,
        analysis: CachedPortfolioAnalysis,
    ) -> None: ...
