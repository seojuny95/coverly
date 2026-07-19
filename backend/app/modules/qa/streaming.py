"""Small SSE protocol helpers shared by QA transports."""

from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.core.generation import GenerationMode
from app.modules.qa.schemas import (
    AnswerCitation,
    PortfolioQuestionResponse,
    QaAnswerStatus,
)
from app.modules.reference_data.contracts import ClaimChannelBlock


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


def response_to_events(response: PortfolioQuestionResponse) -> Iterator[QaStreamEvent]:
    """Turn a completed response into meta → single delta → end.

    Used only for non-streamed fallback paths (agent-unavailable, non-streaming
    ``run()``) where no real per-token deltas were produced by the runtime.
    """

    yield QaMetaEvent(
        type="meta",
        status=response.status,
        generation=response.generation,
    )
    yield QaDeltaEvent(type="delta", text=response.answer)
    yield QaEndEvent(
        type="end",
        status=response.status,
        generation=response.generation,
        citations=response.citations,
        limitations=response.limitations,
        suggestions=response.suggestions,
        claim_channels=response.claim_channels,
    )
