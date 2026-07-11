"""API contracts for grounded, non-RAG portfolio questions."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.consultation import (
    AnswerSection,
    GenerationMode,
    InsuredDemographics,
)
from app.schemas.portfolio import PolicyInput


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1_000)


class PortfolioQuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    policies: list[PolicyInput] = Field(default_factory=list)
    demographics: InsuredDemographics = Field(default_factory=InsuredDemographics)
    history: list[ConversationMessage] = Field(default_factory=list, max_length=30)


class AnswerCitation(BaseModel):
    evidence_id: str | None = None
    policy_id: str | None
    insurer: str | None
    product_name: str | None
    coverage_name: str | None = None


class PortfolioQuestionResponse(BaseModel):
    status: Literal["answered", "refused", "no_data"]
    answer: str
    sections: list[AnswerSection] = Field(default_factory=list)
    citations: list[AnswerCitation]
    limitations: list[str]
    suggestions: list[str] = Field(default_factory=list)
    generation: GenerationMode = "fallback"
    demographics: InsuredDemographics = Field(default_factory=InsuredDemographics)
