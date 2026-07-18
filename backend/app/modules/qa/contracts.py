"""Shared contracts for portfolio consultation features."""

from typing import Literal

from pydantic import BaseModel, Field

Gender = Literal["남성", "여성", "기타", "미상"]
DemographicSource = Literal["policy", "user", "unknown"]
DemographicStatus = Literal[
    "verified_policy",
    "user_provided",
    "conflict_user_override",
    "conflict",
    "missing",
]
GuidanceBasis = Literal["confirmed_fact", "general_guidance"]


class InsuredDemographics(BaseModel):
    """Minimal non-identifying insured context used for personalization."""

    age: int | None = Field(default=None, ge=0, le=120)
    gender: Gender = "미상"
    source: DemographicSource = "unknown"
    status: DemographicStatus = "missing"


class ConsultationEvidence(BaseModel):
    """A fact that may be cited by generated consultation copy."""

    id: str
    fact: str
    source_title: str | None = None
    publisher: str | None = None
    citation_label: str | None = None
    policy_id: str | None = None
    insurer: str | None = None
    product_name: str | None = None
    coverage_name: str | None = None
    amount: int | None = Field(default=None, ge=0)


class AnswerSection(BaseModel):
    title: str
    content: str
    basis: GuidanceBasis
