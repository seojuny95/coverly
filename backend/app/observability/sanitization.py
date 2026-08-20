"""PII-safe trace payload helpers.

Trace payloads are allowlisted at call sites, then passed through this module
as a second guardrail before they can leave the process.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.core.pii import (
    MASKED_RESIDENT_IDENTIFIER,
    mask_email_addresses,
    mask_phone_numbers,
    mask_resident_identifiers,
)
from app.rag.policy.pii import mask_policy_pii

_MAX_TRACE_TEXT_CHARS = 2_000
_SECRET_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "id_token",
        "password",
        "refresh_token",
        "secret",
        "session_id",
        "session_token",
        "token",
    }
)
_SECRET_KEY_SUFFIXES = (
    "api_key",
    "password",
    "secret",
    "session_id",
    "session_token",
    "access_token",
    "refresh_token",
    "id_token",
)


def sanitize_trace_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a JSON-safe, PII-masked copy of an allowlisted trace payload."""

    if not payload:
        return {}
    return {
        key: _sanitize_value(value) for key, value in payload.items() if not _is_secret_key(key)
    }


def mask_trace_text(text: str) -> str:
    """Mask common customer identifiers in a traceable text field."""

    masked = mask_resident_identifiers(text, replacement=MASKED_RESIDENT_IDENTIFIER)
    masked = mask_email_addresses(masked)
    masked = mask_phone_numbers(masked)
    masked = mask_policy_pii(masked)
    return _compact(masked)


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return mask_trace_text(value)
    if isinstance(value, Mapping):
        return sanitize_trace_payload(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_sanitize_value(item) for item in value]
    return mask_trace_text(str(value))


def _is_secret_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in _SECRET_KEYS or any(
        normalized.endswith(f"_{suffix}") for suffix in _SECRET_KEY_SUFFIXES
    )


def _compact(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _MAX_TRACE_TEXT_CHARS:
        return compact
    return f"{compact[:_MAX_TRACE_TEXT_CHARS].rstrip()}..."
