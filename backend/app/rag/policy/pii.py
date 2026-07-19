"""Mask deterministic PII patterns before policy text leaves process memory."""

import re
from collections.abc import Iterable

from app.core.pii import (
    mask_email_addresses,
    mask_phone_numbers,
    mask_resident_identifiers,
)

_VEHICLE_NUMBER_RE = re.compile(r"(?<!\d)\d{2,3}[가-힣]\s?\d{4}(?!\d)")
_LABELED_ACCOUNT_RE = re.compile(
    r"(?P<label>계좌(?:번호)?)\s*[:：]?\s*(?P<value>[0-9][0-9\s-]{7,}[0-9])"
)
_LABELED_IDENTIFIER_RE = re.compile(
    r"(?P<label>증권번호|계약번호|차량번호)\s*[:：]?\s*(?P<value>[^\s|]{4,})"
)
_LABELED_ADDRESS_RE = re.compile(
    r"(?P<label>주[ \t]*소|소재지)[ \t]*(?P<separator>[:：]?)[ \t]*"
    r"(?P<value>[^\n|]{4,})"
)
_NUMBERED_ADDRESS_COMPONENT = r"[가-힣A-Za-z0-9·.-]{1,20}(?:읍|면|동|리|대로|로|길)"
_ADDRESS_VALUE_RE = re.compile(
    rf"(?:^|[ \t])(?:"
    rf"\d{{5}}(?=$|[ \t,])"
    rf"|{_NUMBERED_ADDRESS_COMPONENT}[ \t,]+\d{{1,5}}(?:-\d{{1,5}})?"
    rf")(?=$|[ \t,.-])"
)


def mask_policy_pii(text: str, *, sensitive_values: Iterable[str] = ()) -> str:
    masked = mask_phone_numbers(text)
    masked = mask_email_addresses(masked)
    masked = mask_resident_identifiers(masked)
    masked = _VEHICLE_NUMBER_RE.sub("[차량번호]", masked)
    masked = _mask_labeled_value(masked, _LABELED_ACCOUNT_RE, "[계좌번호]")
    masked = _mask_labeled_value(masked, _LABELED_IDENTIFIER_RE, "[식별번호]")
    masked = _LABELED_ADDRESS_RE.sub(_mask_address_value, masked)
    for value in sorted(_safe_sensitive_values(sensitive_values), key=len, reverse=True):
        masked = masked.replace(value, "[개인정보]")
    return masked


def _mask_labeled_value(text: str, pattern: re.Pattern[str], replacement: str) -> str:
    return pattern.sub(lambda match: f"{match.group('label')} {replacement}", text)


def _mask_address_value(match: re.Match[str]) -> str:
    value = match.group("value")
    if match.group("separator") or _ADDRESS_VALUE_RE.search(value):
        return f"{match.group('label')} [주소]"
    return match.group(0)


def _safe_sensitive_values(values: Iterable[str]) -> set[str]:
    return {value.strip() for value in values if len(value.strip()) >= 2}
