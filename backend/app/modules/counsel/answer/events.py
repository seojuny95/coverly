"""SSE event contracts for a streamed counsel answer."""

import json
from typing import Literal

from pydantic import BaseModel


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


CounselStreamEvent = CounselMetaEvent | CounselDeltaEvent | CounselEndEvent


def serialize_event(event: CounselStreamEvent) -> str:
    return f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
