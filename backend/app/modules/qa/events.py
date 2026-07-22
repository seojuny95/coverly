"""SSE event contracts for a streamed counsel answer."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class CounselMetaEvent(BaseModel):
    type: Literal["meta"] = "meta"
    in_scope: bool

    answered_question: str
    """The question this turn is answering, as the planner tidied it up.

    Not always the history-resolved rewrite: a turn that stands on its own is
    answered as its own sentence, so naming this field after the rewrite would
    describe a value it often does not carry.
    """

    excluded_note: str | None
    """What the planner dropped from the question for being outside insurance."""
    turns_remaining: int


class CounselDeltaEvent(BaseModel):
    type: Literal["delta"] = "delta"
    text: str


class CounselEndEvent(BaseModel):
    type: Literal["end"] = "end"


# Discriminated so the published schema is a strict oneOf: a client validator can
# then reject an event that only loosely resembles one of the shapes.
CounselStreamEvent = Annotated[
    CounselMetaEvent | CounselDeltaEvent | CounselEndEvent,
    Field(discriminator="type"),
]


def serialize_event(event: CounselStreamEvent) -> str:
    return f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
