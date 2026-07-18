"""API contracts for grounded, non-RAG portfolio questions."""

from typing import Literal

from pydantic import BaseModel, Field

from app.core.generation import GenerationMode
from app.modules.portfolio.schemas import ClaimChannelBlock, PortfolioSelectionInput
from app.modules.qa.contracts import (
    AnswerSection,
    InsuredDemographics,
)


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1_000)


class PortfolioQuestionRequest(PortfolioSelectionInput):
    question: str = Field(min_length=1, max_length=500)
    demographics: InsuredDemographics = Field(default_factory=InsuredDemographics)
    history: list[ConversationMessage] = Field(default_factory=list, max_length=30)


class AnswerCitation(BaseModel):
    evidence_id: str | None = None
    policy_id: str | None
    insurer: str | None
    product_name: str | None
    coverage_name: str | None = None
    source_id: str | None = None
    source_title: str | None = None
    source_category: str | None = None
    source_url: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_version: str | None = None


class PortfolioQuestionResponse(BaseModel):
    status: Literal["answered", "refused", "no_data", "clarify"]
    answer: str
    sections: list[AnswerSection] = Field(default_factory=list)
    citations: list[AnswerCitation]
    limitations: list[str]
    suggestions: list[str] = Field(default_factory=list)
    generation: GenerationMode = "fallback"
    demographics: InsuredDemographics = Field(default_factory=InsuredDemographics)
    claim_channels: ClaimChannelBlock | None = None
