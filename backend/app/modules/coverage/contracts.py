"""Shared coverage-domain contracts."""

from typing import Literal

from pydantic import BaseModel, Field

CoverageType = Literal["담보", "부가"]
InsuredGender = Literal["남성", "여성"]
LifeStage = Literal["어린이", "성인", "시니어"]
CoverageDomain = Literal[
    "medical_expense",
    "travel_medical_expense",
    "legal_cost",
    "property_damage",
    "liability",
    "auto",
    "other",
]

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
