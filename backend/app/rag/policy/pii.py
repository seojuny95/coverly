"""Mask deterministic PII patterns before policy text leaves process memory."""

import re
from collections.abc import Iterable

_PHONE_RE = re.compile(
    r"(?<!\d)(?:(?:01[016789]|02|0[3-6][1-5])-?\d{3,4}-?\d{4}|1[568]\d{2}-?\d{4})(?!\d)"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RRN_RE = re.compile(r"\b\d{6}-?[1-4]\d{6}\b")
_VEHICLE_NUMBER_RE = re.compile(r"(?<!\d)\d{2,3}[가-힣]\s?\d{4}(?!\d)")
_LABELED_ACCOUNT_RE = re.compile(
    r"(?P<label>계좌(?:번호)?)\s*[:：]?\s*(?P<value>[0-9][0-9\s-]{7,}[0-9])"
)
_LABELED_IDENTIFIER_RE = re.compile(
    r"(?P<label>증권번호|계약번호|차량번호)\s*[:：]?\s*(?P<value>[^\s|]{4,})"
)
_LABELED_ADDRESS_RE = re.compile(r"(?P<label>주소|소재지)\s*[:：]?\s*(?P<value>[^\n|]{4,})")


def mask_policy_pii(text: str, *, sensitive_values: Iterable[str] = ()) -> str:
    masked = _PHONE_RE.sub("[전화번호]", text)
    masked = _EMAIL_RE.sub("[이메일]", masked)
    masked = _RRN_RE.sub("[주민등록번호]", masked)
    masked = _VEHICLE_NUMBER_RE.sub("[차량번호]", masked)
    masked = _mask_labeled_value(masked, _LABELED_ACCOUNT_RE, "[계좌번호]")
    masked = _mask_labeled_value(masked, _LABELED_IDENTIFIER_RE, "[식별번호]")
    masked = _mask_labeled_value(masked, _LABELED_ADDRESS_RE, "[주소]")
    for value in sorted(_safe_sensitive_values(sensitive_values), key=len, reverse=True):
        masked = masked.replace(value, "[개인정보]")
    return masked


def _mask_labeled_value(text: str, pattern: re.Pattern[str], replacement: str) -> str:
    return pattern.sub(lambda match: f"{match.group('label')} {replacement}", text)


def _safe_sensitive_values(values: Iterable[str]) -> set[str]:
    return {value.strip() for value in values if len(value.strip()) >= 2}
