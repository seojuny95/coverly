"""Mask user-entered PII before QA text crosses a model boundary."""

from app.core.pii import (
    MASKED_RESIDENT_IDENTIFIER,
    mask_email_addresses,
    mask_phone_numbers,
    mask_resident_identifiers,
)


def mask_qa_pii(text: str) -> str:
    """Mask resident identifiers, phone numbers, and email addresses."""

    masked = mask_resident_identifiers(
        text,
        replacement=MASKED_RESIDENT_IDENTIFIER,
    )
    masked = mask_email_addresses(masked)
    return mask_phone_numbers(masked)
