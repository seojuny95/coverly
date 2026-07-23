"""Request/response contracts for the qa use case."""

from typing import Literal

from pydantic import BaseModel, Field

MAX_QA_QUESTION_CHARACTERS = 2_000
MAX_QA_MESSAGE_CHARACTERS = 4_000
MAX_QA_HISTORY_MESSAGES = 40
MAX_QA_SESSION_TOKEN_CHARACTERS = 512


class QaMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_QA_MESSAGE_CHARACTERS)


class QaRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QA_QUESTION_CHARACTERS)
    history: list[QaMessage] = Field(
        default_factory=list,
        max_length=MAX_QA_HISTORY_MESSAGES,
    )
    session_id: str = Field(
        min_length=1,
        max_length=MAX_QA_SESSION_TOKEN_CHARACTERS,
    )
