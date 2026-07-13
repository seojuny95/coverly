"""Signed bearer tokens for short-lived uploaded-policy RAG sessions."""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.settings import get_settings

_TOKEN_VERSION = "v1"
_FALLBACK_SECRET = uuid.uuid4().hex
_MIN_CONFIGURED_SECRET_BYTES = 32
_PLACEHOLDER_SECRETS = {
    "replace-with-random-secret",
    "change-me",
    "changeme",
}


class InvalidPolicySessionToken(Exception):
    """The client supplied a forged, malformed, or expired policy session token."""


@dataclass(frozen=True)
class PolicySessionClaims:
    session_id: str
    expires_at: datetime
    max_expires_at: datetime


def sign_policy_session_id(
    session_id: str,
    expires_at: datetime,
    *,
    max_expires_at: datetime | None = None,
    secret: str | None = None,
) -> str:
    expires_epoch = _to_epoch_seconds(expires_at)
    max_expires_epoch = _to_epoch_seconds(max_expires_at or expires_at)
    payload = f"{_TOKEN_VERSION}.{session_id}.{expires_epoch}.{max_expires_epoch}"
    signature = _signature(payload, _active_secret(secret))
    return f"{payload}.{signature}"


def verify_policy_session_token(
    token: str,
    *,
    secret: str | None = None,
    now: datetime | None = None,
) -> str:
    return verify_policy_session_claims(token, secret=secret, now=now).session_id


def verify_policy_session_claims(
    token: str,
    *,
    secret: str | None = None,
    now: datetime | None = None,
) -> PolicySessionClaims:
    parts = token.split(".")
    if len(parts) != 5:
        raise InvalidPolicySessionToken

    version, session_id, expires_raw, max_expires_raw, supplied_signature = parts
    if version != _TOKEN_VERSION or not session_id:
        raise InvalidPolicySessionToken

    try:
        expires_epoch = int(expires_raw)
        max_expires_epoch = int(max_expires_raw)
    except ValueError as exc:
        raise InvalidPolicySessionToken from exc
    if expires_epoch > max_expires_epoch:
        raise InvalidPolicySessionToken

    payload = f"{version}.{session_id}.{expires_epoch}.{max_expires_epoch}"
    expected_signature = _signature(payload, _active_secret(secret))
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise InvalidPolicySessionToken

    current = now or datetime.now(UTC)
    current_epoch = _to_epoch_seconds(current)
    if current_epoch > expires_epoch or current_epoch > max_expires_epoch:
        raise InvalidPolicySessionToken

    return PolicySessionClaims(
        session_id=session_id,
        expires_at=datetime.fromtimestamp(expires_epoch, tz=UTC),
        max_expires_at=datetime.fromtimestamp(max_expires_epoch, tz=UTC),
    )


def verified_policy_session_ids(tokens: list[str]) -> list[str]:
    session_ids: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        try:
            session_id = verify_policy_session_token(token)
        except InvalidPolicySessionToken:
            continue
        if session_id in seen:
            continue
        session_ids.append(session_id)
        seen.add(session_id)
    return session_ids


def ensure_policy_session_secret_configured() -> None:
    _active_secret(None)


def _active_secret(secret: str | None) -> str:
    if secret is not None:
        return secret

    settings = get_settings()
    if settings.policy_rag_session_secret:
        _validate_configured_secret(settings.policy_rag_session_secret)
        return settings.policy_rag_session_secret
    if settings.database_url:
        raise RuntimeError("POLICY_RAG_SESSION_SECRET is required when DATABASE_URL is configured")
    return _FALLBACK_SECRET


def _validate_configured_secret(secret: str) -> None:
    normalized = secret.strip()
    if normalized.lower() in _PLACEHOLDER_SECRETS:
        raise RuntimeError(
            "POLICY_RAG_SESSION_SECRET must be replaced with a random secret before use"
        )
    if len(normalized.encode()) < _MIN_CONFIGURED_SECRET_BYTES:
        raise RuntimeError("POLICY_RAG_SESSION_SECRET must be at least 32 bytes")


def _signature(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _to_epoch_seconds(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())
