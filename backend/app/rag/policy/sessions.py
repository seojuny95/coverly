"""Lifecycle operations for uploaded-policy RAG session tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.integrations.postgres.policy_rag_store import shared_policy_store
from app.rag.policy.session_tokens import (
    InvalidPolicySessionToken,
    sign_policy_session_id,
    verify_policy_session_claims,
)
from app.rag.policy.store import PolicyRagStore


@dataclass(frozen=True)
class RefreshedPolicySession:
    token: str
    expires_at: datetime


def delete_policy_session(session_token: str) -> None:
    claims = verify_policy_session_claims(session_token)
    shared_policy_store().delete(claims.session_id)


def refresh_policy_session(
    session_token: str,
    *,
    store: PolicyRagStore | None = None,
    now: datetime | None = None,
) -> RefreshedPolicySession:
    current = now or datetime.now(UTC)
    claims = verify_policy_session_claims(session_token, now=current)
    settings = get_settings()

    next_expires_at = min(
        current + timedelta(seconds=settings.policy_rag_ttl_seconds),
        claims.max_expires_at,
    )
    if next_expires_at <= current:
        raise InvalidPolicySessionToken

    active_store = store or shared_policy_store()
    if not active_store.extend(claims.session_id, next_expires_at):
        raise InvalidPolicySessionToken

    return RefreshedPolicySession(
        token=sign_policy_session_id(
            claims.session_id,
            next_expires_at,
            max_expires_at=claims.max_expires_at,
        ),
        expires_at=next_expires_at,
    )
