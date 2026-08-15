"""Create one isolated runtime session from the precomputed sample fixture."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.diagnostics import safe_exception_context
from app.modules.policy.schemas import PolicyParseResponse
from app.modules.portfolio.sample.fixture import load_sample_portfolio_fixture
from app.modules.portfolio.sample.preparation import prepare_sample_portfolio
from app.modules.portfolio.session.models import NewPortfolioSession
from app.modules.portfolio.session.repository import PortfolioSessionRepository
from app.rag.policy.session_tokens import (
    ensure_policy_session_secret_configured,
    sign_policy_session_id,
)
from app.rag.policy.store import PolicyRagStore

logger = logging.getLogger(__name__)


class SamplePortfolioUnavailable(Exception):
    """The precomputed sample portfolio cannot be prepared safely."""


@dataclass(frozen=True)
class CreatedSamplePortfolio:
    token: str
    expires_at: datetime
    documents: tuple[tuple[str, PolicyParseResponse], ...]


def create_sample_portfolio(
    repository: PortfolioSessionRepository,
    rag_store: PolicyRagStore,
    *,
    now: datetime | None = None,
) -> CreatedSamplePortfolio:
    created_at = now or datetime.now(UTC)
    rag_session_ids: tuple[str, ...] = ()
    session_id: str | None = None
    session_created = False
    rag_seed_started = False
    try:
        rag_store.delete_expired(created_at)
    except Exception as exc:
        logger.warning(
            "Expired sample portfolio RAG cleanup failed with %s",
            type(exc).__name__,
        )
    try:
        ensure_policy_session_secret_configured()
        settings = get_settings()
        fixture = load_sample_portfolio_fixture()
        if (
            fixture.embedding_model != settings.openai_embedding_model
            or fixture.embedding_dimensions != settings.openai_embedding_dimensions
        ):
            raise ValueError("Sample embeddings do not match runtime settings")

        expires_at = created_at + timedelta(seconds=settings.policy_rag_ttl_seconds)
        max_expires_at = created_at + timedelta(seconds=settings.policy_rag_max_ttl_seconds)
        session_id = uuid.uuid4().hex
        document_ids = tuple(uuid.uuid4().hex for _ in fixture.policies)
        rag_session_ids = tuple(uuid.uuid4().hex for _ in fixture.policies)
        prepared = prepare_sample_portfolio(
            fixture,
            document_ids=document_ids,
            rag_session_ids=rag_session_ids,
            created_at=created_at,
            expires_at=expires_at,
        )
        token = sign_policy_session_id(
            session_id,
            expires_at,
            max_expires_at=max_expires_at,
        )
        repository.create_seeded(
            NewPortfolioSession(
                id=session_id,
                created_at=created_at,
                expires_at=expires_at,
                max_expires_at=max_expires_at,
                kind="sample",
                version=fixture.portfolio_version,
            ),
            prepared.documents,
            prepared.analyses,
            max_active_sample_sessions=settings.sample_portfolio_max_active_sessions,
        )
        session_created = True
        rag_seed_started = True
        rag_store.add(prepared.rag_records)
    except Exception as exc:
        if session_created and session_id is not None:
            _delete_seeded_session(repository, session_id)
        if rag_seed_started:
            _delete_rag_sessions(rag_store, rag_session_ids)
        logger.error("sample_portfolio_creation_failed", extra=safe_exception_context(exc))
        raise SamplePortfolioUnavailable from exc

    return CreatedSamplePortfolio(
        token=token,
        expires_at=expires_at,
        documents=prepared.public_documents,
    )


def _delete_rag_sessions(
    rag_store: PolicyRagStore,
    rag_session_ids: tuple[str, ...],
) -> None:
    for rag_session_id in rag_session_ids:
        try:
            rag_store.delete(rag_session_id)
        except Exception as exc:
            logger.warning(
                "Sample portfolio RAG cleanup failed with %s",
                type(exc).__name__,
            )


def _delete_seeded_session(
    repository: PortfolioSessionRepository,
    session_id: str,
) -> None:
    try:
        repository.delete(session_id)
    except Exception as exc:
        logger.warning(
            "Sample portfolio session cleanup failed with %s",
            type(exc).__name__,
        )
