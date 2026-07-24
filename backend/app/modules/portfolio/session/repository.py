"""Persistence protocol for portfolio sessions."""

from datetime import datetime
from typing import Literal, Protocol

from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    NewPortfolioSession,
    PolicyDocumentReservation,
    PortfolioSessionSnapshot,
    StoredPolicyDocument,
)

ReserveDocumentResult = Literal[
    "reserved",
    "in_progress",
    "completed",
    "missing",
    "limit_exceeded",
    "cancelled",
]
CompleteDocumentResult = Literal["stored", "missing", "cancelled"]


class PortfolioPolicySelectionNotFound(Exception):
    """One or more requested policy documents do not belong to the session."""


class PortfolioSessionRepositoryUnavailable(Exception):
    """The session store is temporarily unavailable."""


class PortfolioSessionRepository(Protocol):
    def check_ready(self) -> None:
        """Raise when the backing session store cannot serve requests."""
        ...

    def create(self, session: NewPortfolioSession) -> None: ...

    def consume_counsel_turn(
        self,
        session_id: str,
        *,
        now: datetime,
        max_turns: int,
    ) -> int | None:
        """Claim one counsel turn, returning how many remain.

        None means the session is gone or the cap is already reached. The check
        and the increment happen together so two concurrent requests cannot both
        take the last turn.
        """
        ...

    def refund_counsel_turn(
        self,
        session_id: str,
        *,
        now: datetime,
        max_turns: int,
    ) -> int | None:
        """Return one turn and report the restored allowance atomically."""
        ...

    def reserve_document(
        self,
        session_id: str,
        document_id: str,
        reservation_id: str,
        *,
        now: datetime,
        expires_at: datetime,
        max_documents: int,
    ) -> ReserveDocumentResult: ...

    def complete_document(
        self,
        reservation: PolicyDocumentReservation,
        document: StoredPolicyDocument,
        *,
        now: datetime,
    ) -> CompleteDocumentResult: ...

    def release_document(self, reservation: PolicyDocumentReservation) -> None: ...

    def counsel_turns_remaining(
        self,
        session_id: str,
        *,
        now: datetime,
        max_turns: int,
    ) -> int | None:
        """How many counsel turns this session has left, or None if it is gone."""
        ...

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
