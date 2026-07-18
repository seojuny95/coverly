"""Small SSE protocol helpers shared by QA transports."""

import re
from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.core.generation import GenerationMode
from app.modules.portfolio.schemas import ClaimChannelBlock
from app.modules.qa.schemas import (
    AnswerCitation,
    PortfolioQuestionResponse,
    QaAnswerStatus,
)

_STREAM_CHUNK_SIZE = 16


class QaProgressEvent(BaseModel):
    type: Literal["progress"]
    stage: str
    text: str


class QaMetaEvent(BaseModel):
    type: Literal["meta"]
    status: QaAnswerStatus
    generation: GenerationMode


class QaDeltaEvent(BaseModel):
    type: Literal["delta"]
    text: str


class QaEndEvent(BaseModel):
    type: Literal["end"]
    status: QaAnswerStatus
    generation: GenerationMode
    citations: list[AnswerCitation]
    limitations: list[str]
    suggestions: list[str]
    claim_channels: ClaimChannelBlock | None


QaStreamEvent = Annotated[
    QaProgressEvent | QaMetaEvent | QaDeltaEvent | QaEndEvent,
    Field(discriminator="type"),
]


def answer_text_chunks(text: str) -> Iterator[str]:
    """Split completed answers into stable display-sized SSE deltas."""

    buffer = ""
    for token in re.findall(r"\S+\s*", text):
        while len(token) > _STREAM_CHUNK_SIZE:
            if buffer:
                yield buffer
                buffer = ""
            yield token[:_STREAM_CHUNK_SIZE]
            token = token[_STREAM_CHUNK_SIZE:]
        if buffer and len(buffer) + len(token) > _STREAM_CHUNK_SIZE:
            yield buffer
            buffer = ""
        buffer += token
    if buffer:
        yield buffer


def stream_response(response: PortfolioQuestionResponse) -> Iterator[QaStreamEvent]:
    yield QaMetaEvent(
        type="meta",
        status=response.status,
        generation=response.generation,
    )
    for chunk in answer_text_chunks(response.answer):
        yield QaDeltaEvent(type="delta", text=chunk)
    yield QaEndEvent(
        type="end",
        status=response.status,
        generation=response.generation,
        citations=response.citations,
        limitations=response.limitations,
        suggestions=response.suggestions,
        claim_channels=response.claim_channels,
    )
