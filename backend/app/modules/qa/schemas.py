"""API contracts for grounded, non-RAG portfolio questions."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.generation import GenerationMode
from app.modules.consultation.contracts import InsuredDemographics
from app.modules.portfolio.schemas import PortfolioSelectionInput
from app.modules.qa.contracts import AnswerSection
from app.modules.reference_data.contracts import ClaimChannelBlock


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1_000)


QA_HISTORY_LIMIT = 12
QA_HISTORY_CONTENT_LIMIT = 1_000
type QaAnswerStatus = Literal["answered", "refused", "no_data", "clarify"]


class PortfolioQuestionRequest(PortfolioSelectionInput):
    question: str = Field(min_length=1, max_length=500)
    demographics: InsuredDemographics = Field(default_factory=InsuredDemographics)
    history: list[ConversationMessage] = Field(default_factory=list)

    @field_validator("history", mode="before")
    @classmethod
    def keep_recent_history(cls, value: object) -> object:
        if not isinstance(value, list):
            return value

        normalized: list[object] = []
        for item in value[-QA_HISTORY_LIMIT:]:
            if not isinstance(item, dict) or not isinstance(item.get("content"), str):
                normalized.append(item)
                continue
            message = dict(item)
            message["content"] = item["content"][:QA_HISTORY_CONTENT_LIMIT]
            normalized.append(message)
        return normalized


def recent_history(
    history: list[ConversationMessage] | None,
) -> list[ConversationMessage]:
    return (history or [])[-QA_HISTORY_LIMIT:]


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
    status: QaAnswerStatus
    answer: str
    sections: list[AnswerSection] = Field(default_factory=list)
    citations: list[AnswerCitation]
    limitations: list[str]
    suggestions: list[str] = Field(default_factory=list)
    generation: GenerationMode = "fallback"
    demographics: InsuredDemographics = Field(default_factory=InsuredDemographics)
    claim_channels: ClaimChannelBlock | None = None
