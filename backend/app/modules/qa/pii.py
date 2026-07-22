"""Mask user-entered PII before qa text crosses the model boundary.

The question and the conversation history are client text: a user can type a
resident registration number, a phone number, or an email into the chat. Those
must not reach an external model, and everything sent there is also what a
tracing exporter would carry off.
"""

from app.core.pii import (
    MASKED_RESIDENT_IDENTIFIER,
    mask_email_addresses,
    mask_phone_numbers,
    mask_resident_identifiers,
)
from app.modules.qa.schemas import QaMessage


def mask_qa_pii(text: str) -> str:
    """Mask resident identifiers, phone numbers, and email addresses."""

    masked = mask_resident_identifiers(text, replacement=MASKED_RESIDENT_IDENTIFIER)
    masked = mask_email_addresses(masked)
    return mask_phone_numbers(masked)


def masked_history(history: list[QaMessage]) -> list[QaMessage]:
    """Mask every turn, keeping roles so the agent still reads the exchange."""

    return [
        message.model_copy(update={"content": mask_qa_pii(message.content)}) for message in history
    ]
