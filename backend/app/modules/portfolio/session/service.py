"""Application service for signed portfolio sessions."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from app.core.config import get_settings
from app.integrations.postgres.policy_rag_store import shared_policy_store
from app.integrations.postgres.portfolio_session_store import PgPortfolioSessionRepository
from app.modules.policy.pipeline import PipelineResult
from app.modules.portfolio.session.models import (
    CachedPortfolioAnalysis,
    NewPortfolioSession,
    PolicyDocumentReservation,
    PortfolioSessionSnapshot,
    StoredPolicyDocument,
)
from app.modules.portfolio.session.policy_projection import (
    policy_for_storage,
    rag_session_id_from_result,
)
from app.modules.portfolio.session.repository import PortfolioSessionRepository
from app.rag.policy.session_tokens import (
    InvalidPolicySessionToken,
    PolicySessionClaims,
    ensure_policy_session_secret_configured,
    sign_policy_session_id,
    verify_policy_session_claims,
)
from app.rag.policy.store import PolicyRagStore

logger = logging.getLogger(__name__)


class InvalidPortfolioSessionToken(InvalidPolicySessionToken):
    """The portfolio session is invalid, expired, or no longer stored."""


class PortfolioSessionDocumentLimitExceeded(Exception):
    """The portfolio already contains the maximum number of documents."""


class PortfolioSessionDocumentCancelled(Exception):
    """The client cancelled this document before parsing completed."""


@dataclass(frozen=True)
class PortfolioSessionAccess:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class RegisteredPolicyDocument:
    id: str


class PortfolioSessionService:
    def __init__(
        self,
        repository: PortfolioSessionRepository,
        *,
        rag_store: PolicyRagStore,
    ) -> None:
        self._repository = repository
        self._rag_store = rag_store

    def create(self, *, now: datetime | None = None) -> PortfolioSessionAccess:
        ensure_policy_session_secret_configured()
        created_at = now or datetime.now(UTC)
        settings = get_settings()
        try:
            self._rag_store.delete_expired(created_at)
        except Exception as exc:
            logger.warning(
                "Expired portfolio RAG cleanup failed with %s",
                type(exc).__name__,
            )
        expires_at = created_at + timedelta(seconds=settings.policy_rag_ttl_seconds)
        max_expires_at = created_at + timedelta(seconds=settings.policy_rag_max_ttl_seconds)
        session_id = uuid.uuid4().hex
        self._repository.create(
            NewPortfolioSession(
                id=session_id,
                created_at=created_at,
                expires_at=expires_at,
                max_expires_at=max_expires_at,
            )
        )
        return PortfolioSessionAccess(
            token=sign_policy_session_id(
                session_id,
                expires_at,
                max_expires_at=max_expires_at,
            ),
            expires_at=expires_at,
        )

    def add_pipeline_result(
        self,
        token: str,
        result: PipelineResult,
        *,
        document_id: str | None = None,
        now: datetime | None = None,
    ) -> RegisteredPolicyDocument:
        current = now or datetime.now(UTC)
        try:
            reservation = self.begin_upload(
                token,
                document_id=document_id,
                now=current,
            )
        except Exception:
            rag_session_id = rag_session_id_from_result(result, now=current)
            if rag_session_id is not None:
                self._delete_rag_session(rag_session_id)
            raise
        return self.complete_upload(reservation, result, now=current)

    def begin_upload(
        self,
        token: str,
        *,
        document_id: str | None = None,
        now: datetime | None = None,
    ) -> PolicyDocumentReservation:
        current = now or datetime.now(UTC)
        claims = self._verify(token, now=current)
        resolved_document_id = document_id or uuid.uuid4().hex
        reserved = self._repository.reserve_document(
            claims.session_id,
            resolved_document_id,
            now=current,
            max_documents=get_settings().portfolio_session_max_documents,
        )
        if reserved == "limit_exceeded":
            raise PortfolioSessionDocumentLimitExceeded
        if reserved == "cancelled":
            raise PortfolioSessionDocumentCancelled
        if reserved == "missing":
            raise InvalidPortfolioSessionToken
        return PolicyDocumentReservation(
            session_id=claims.session_id,
            document_id=resolved_document_id,
        )

    def complete_upload(
        self,
        reservation: PolicyDocumentReservation,
        result: PipelineResult,
        *,
        now: datetime | None = None,
    ) -> RegisteredPolicyDocument:
        current = now or datetime.now(UTC)
        rag_session_id = rag_session_id_from_result(result, now=current)
        try:
            policy = policy_for_storage(result, document_id=reservation.document_id)
            stored = self._repository.complete_document(
                reservation,
                StoredPolicyDocument(
                    id=reservation.document_id,
                    policy=policy,
                    rag_session_id=rag_session_id,
                ),
                now=current,
            )
        except Exception:
            self._discard_upload(reservation, rag_session_id=rag_session_id)
            raise
        if stored != "stored":
            self._discard_upload(reservation, rag_session_id=rag_session_id)
            if stored == "cancelled":
                raise PortfolioSessionDocumentCancelled
            raise InvalidPortfolioSessionToken
        return RegisteredPolicyDocument(id=reservation.document_id)

    def release_upload(self, reservation: PolicyDocumentReservation) -> None:
        try:
            self._repository.release_document(reservation)
        except Exception as exc:
            logger.warning(
                "Portfolio document reservation release failed with %s",
                type(exc).__name__,
            )

    def snapshot(
        self,
        token: str,
        *,
        policy_ids: list[str] | None = None,
        now: datetime | None = None,
    ) -> PortfolioSessionSnapshot:
        current = now or datetime.now(UTC)
        claims = self._verify(token, now=current)
        selected_ids = tuple(dict.fromkeys(policy_ids)) if policy_ids else None
        snapshot = self._repository.snapshot(
            claims.session_id,
            policy_ids=selected_ids,
            now=current,
        )
        if snapshot is None:
            raise InvalidPortfolioSessionToken
        return snapshot

    def refresh(
        self,
        token: str,
        *,
        now: datetime | None = None,
    ) -> PortfolioSessionAccess:
        current = now or datetime.now(UTC)
        claims = self._verify(token, now=current)
        settings = get_settings()
        next_expires_at = min(
            current + timedelta(seconds=settings.policy_rag_ttl_seconds),
            claims.max_expires_at,
        )
        if next_expires_at <= current:
            raise InvalidPortfolioSessionToken
        rag_session_ids = self._repository.extend(
            claims.session_id,
            next_expires_at,
            now=current,
        )
        if rag_session_ids is None:
            raise InvalidPortfolioSessionToken
        for rag_session_id in rag_session_ids:
            try:
                self._rag_store.extend(rag_session_id, next_expires_at)
            except Exception as exc:
                logger.warning(
                    "Portfolio RAG session refresh failed with %s",
                    type(exc).__name__,
                )
        return PortfolioSessionAccess(
            token=sign_policy_session_id(
                claims.session_id,
                next_expires_at,
                max_expires_at=claims.max_expires_at,
            ),
            expires_at=next_expires_at,
        )

    def delete(self, token: str, *, now: datetime | None = None) -> None:
        claims = self._verify(token, now=now or datetime.now(UTC))
        rag_session_ids = self._repository.delete(claims.session_id)
        if rag_session_ids is None:
            raise InvalidPortfolioSessionToken
        for rag_session_id in rag_session_ids:
            self._delete_rag_session(rag_session_id)

    def delete_documents(
        self,
        token: str,
        document_ids: list[str],
        *,
        now: datetime | None = None,
    ) -> None:
        current = now or datetime.now(UTC)
        claims = self._verify(token, now=current)
        selected_ids = tuple(dict.fromkeys(document_ids))
        rag_session_ids = self._repository.delete_documents(
            claims.session_id,
            selected_ids,
            now=current,
        )
        if rag_session_ids is None:
            raise InvalidPortfolioSessionToken
        for rag_session_id in rag_session_ids:
            self._delete_rag_session(rag_session_id)

    def close(self) -> None:
        if isinstance(self._repository, PgPortfolioSessionRepository):
            self._repository.close()

    def load_cached_analysis(
        self,
        snapshot: PortfolioSessionSnapshot,
        *,
        context_hash: str,
    ) -> CachedPortfolioAnalysis | None:
        return self._repository.load_cached_analysis(
            snapshot.session_id,
            version=snapshot.version,
            context_hash=context_hash,
        )

    def save_cached_analysis(
        self,
        snapshot: PortfolioSessionSnapshot,
        analysis: CachedPortfolioAnalysis,
    ) -> None:
        self._repository.save_cached_analysis(snapshot.session_id, analysis)

    @staticmethod
    def _verify(token: str, *, now: datetime) -> PolicySessionClaims:
        try:
            return verify_policy_session_claims(token, now=now)
        except InvalidPolicySessionToken as exc:
            raise InvalidPortfolioSessionToken from exc

    def _delete_rag_session(self, rag_session_id: str) -> None:
        try:
            self._rag_store.delete(rag_session_id)
        except Exception as exc:
            logger.warning(
                "Portfolio RAG session deletion failed with %s",
                type(exc).__name__,
            )

    def _discard_upload(
        self,
        reservation: PolicyDocumentReservation,
        *,
        rag_session_id: str | None,
    ) -> None:
        self.release_upload(reservation)
        if rag_session_id is not None:
            self._delete_rag_session(rag_session_id)


@lru_cache(maxsize=1)
def shared_portfolio_session_service() -> PortfolioSessionService:
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for portfolio sessions")
    return PortfolioSessionService(
        PgPortfolioSessionRepository(settings.database_url),
        rag_store=shared_policy_store(),
    )
