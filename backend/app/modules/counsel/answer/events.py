"""SSE event contracts for a streamed counsel answer."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class CounselMetaEvent(BaseModel):
    type: Literal["meta"] = "meta"
    in_scope: bool
    rewritten_question: str
    excluded_note: str | None


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
