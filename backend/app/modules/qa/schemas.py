"""Request/response contracts for the qa use case."""

from typing import Literal

from pydantic import BaseModel, Field


class QaMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class QaRequest(BaseModel):
    question: str = Field(min_length=1)
    history: list[QaMessage] = Field(default_factory=list)
    session_id: str = Field(min_length=1)
