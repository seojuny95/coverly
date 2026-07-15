"""API contracts for grounded, non-RAG portfolio questions."""

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.contracts import (
    AnswerSection,
    GenerationMode,
    InsuredDemographics,
)


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
    source_id: str | None = None
    source_title: str | None = None
    source_category: str | None = None
    source_url: str | None = None
    source_page: int | None = Field(default=None, ge=1)
    source_version: str | None = None


class ClaimChannelLink(BaseModel):
    label: str
    url: str


class ClaimChannelInsurer(BaseModel):
    name: str
    customer_center: str | None = None
    note: str | None = None
    links: list[ClaimChannelLink] = Field(default_factory=list)


class ClaimChannelMedicalIndemnity(BaseModel):
    name: str
    description: str | None = None
    call_center: str | None = None
    links: list[ClaimChannelLink] = Field(default_factory=list)


class ClaimChannelBlock(BaseModel):
    insurers: list[ClaimChannelInsurer] = Field(default_factory=list)
    medical_indemnity: ClaimChannelMedicalIndemnity | None = None


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
