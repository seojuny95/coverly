"""Shared deterministic primitives for masking common PII shapes."""

import re
from collections.abc import Iterator

MASKED_RESIDENT_IDENTIFIER = "******-*******"

# Masking is deliberately shape-based rather than validity-based. Invalid or
# partially redacted identifiers are still sensitive and must not cross an
# external boundary unchanged.
_FORMATTED_RESIDENT_IDENTIFIER = re.compile(
    r"(?<!\d)"
    r"(?P<birth>\d{6})"
    r"(?:\s*-\s*|\s+)"
    r"(?P<code>\d)"
    r"(?P<tail>[\d*]{0,6})"
    r"(?![\d*])"
)
_COMPACT_RESIDENT_IDENTIFIER = re.compile(
    r"(?<!\d)"
    r"(?P<birth>\d{6})"
    r"(?P<code>\d)"
    r"(?P<tail>[\d*]{6})"
    r"(?![\d*])"
)
_RESIDENT_IDENTIFIER_PATTERNS = (
    _FORMATTED_RESIDENT_IDENTIFIER,
    _COMPACT_RESIDENT_IDENTIFIER,
)

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:(?:01[016789]|02|0[3-6][1-5])[-.\s]?\d{3,4}[-.\s]?\d{4}|"
    r"1[568]\d{2}[-.\s]?\d{4})(?!\d)"
)


def iter_resident_identifier_matches(text: str) -> Iterator[re.Match[str]]:
    """Yield resident-identifier-shaped matches in source order."""

    matches = [
        match for pattern in _RESIDENT_IDENTIFIER_PATTERNS for match in pattern.finditer(text)
    ]
    matches.sort(key=lambda match: match.start())
    yield from matches


def mask_resident_identifiers(
    text: str,
    *,
    replacement: str = "[주민등록번호]",
) -> str:
    """Mask all resident-identifier-shaped values in text."""

    masked = text
    for pattern in _RESIDENT_IDENTIFIER_PATTERNS:
        masked = pattern.sub(replacement, masked)
    return masked


def mask_email_addresses(text: str, *, replacement: str = "[이메일]") -> str:
    """Mask email-address-shaped values in text."""

    return _EMAIL_PATTERN.sub(replacement, text)


def mask_phone_numbers(text: str, *, replacement: str = "[전화번호]") -> str:
    """Mask supported Korean phone-number shapes in text."""

    return _PHONE_PATTERN.sub(replacement, text)
