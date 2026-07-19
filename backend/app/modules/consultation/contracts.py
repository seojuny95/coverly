"""Provider-neutral contracts shared by analysis and question answering."""

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


class InsuredDemographics(BaseModel):
    """Minimal non-identifying insured context used for personalization."""

    age: int | None = Field(default=None, ge=0, le=120)
    gender: Gender = "미상"
    source: DemographicSource = "unknown"
    status: DemographicStatus = "missing"


class ConsultationEvidence(BaseModel):
    """A fact that generated consultation copy may cite."""

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
