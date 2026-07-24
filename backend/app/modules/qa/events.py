"""SSE event contracts for a streamed qa answer."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class QaMetaEvent(BaseModel):
    type: Literal["meta"] = "meta"
    in_scope: bool

    answered_question: str
    """The question this turn is answering.

    See route.py's module docstring for why this and the two fields below carry
    placeholder values today rather than values from a dedicated scoping step.
    """

    excluded_note: str | None
    """What was dropped from the question for being outside insurance, if anything."""
    turns_remaining: int


class QaDeltaEvent(BaseModel):
    type: Literal["delta"] = "delta"
    text: str


class QaEndEvent(BaseModel):
    type: Literal["end"] = "end"


class QaErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: Literal["QA_STREAM_FAILED"]
    message: str
    request_id: str
    retryable: bool


# Discriminated so the published schema is a strict oneOf: a client validator can
# then reject an event that only loosely resembles one of the shapes.
QaStreamEvent = Annotated[
    QaMetaEvent | QaDeltaEvent | QaEndEvent | QaErrorEvent,
    Field(discriminator="type"),
]


def serialize_event(event: QaStreamEvent) -> str:
    return f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
