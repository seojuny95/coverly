"""Mask deterministic PII patterns before policy text leaves process memory."""

import re

_PHONE_RE = re.compile(
    r"(?<!\d)(?:(?:01[016789]|02|0[3-6][1-5])-?\d{3,4}-?\d{4}|1[568]\d{2}-?\d{4})(?!\d)"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RRN_RE = re.compile(r"\b\d{6}-?[1-4]\d{6}\b")


def mask_policy_pii(text: str) -> str:
    masked = _PHONE_RE.sub("[전화번호]", text)
    masked = _EMAIL_RE.sub("[이메일]", masked)
    return _RRN_RE.sub("[주민등록번호]", masked)
