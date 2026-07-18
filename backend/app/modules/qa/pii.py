"""Mask user-entered PII before QA text crosses a model boundary."""

import re

from app.modules.policy.demographics import mask_demographic_identifiers

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:(?:01[016789]|02|0[3-6][1-5])[-.\s]?\d{3,4}[-.\s]?\d{4}|"
    r"1[568]\d{2}[-.\s]?\d{4})(?!\d)"
)


def mask_qa_pii(text: str) -> str:
    """Mask resident identifiers, phone numbers, and email addresses."""

    masked = mask_demographic_identifiers(text)
    masked = _EMAIL_PATTERN.sub("[이메일]", masked)
    return _PHONE_PATTERN.sub("[전화번호]", masked)
