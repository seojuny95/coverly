"""API contracts for non-RAG portfolio questions."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.portfolio import PolicyInput


class PortfolioQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    policies: list[PolicyInput] = Field(default_factory=list)


class AnswerCitation(BaseModel):
    policy_id: str | None
    insurer: str | None
    product_name: str | None
    coverage_name: str | None = None


class PortfolioQuestionResponse(BaseModel):
    status: Literal["answered", "refused", "no_data"]
    answer: str
    citations: list[AnswerCitation]
    limitations: list[str]
