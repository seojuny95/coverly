"""API contracts for deterministic portfolio analysis."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.portfolio import PolicyInput


class PortfolioAnalysisRequest(BaseModel):
    policies: list[PolicyInput] = Field(default_factory=list)
    age: int = Field(ge=0, le=120)
    gender: Literal["남성", "여성", "기타", "미상"] = "미상"


class CoverageGap(BaseModel):
    category: str
    reason: str


class AnalysisSource(BaseModel):
    policy_id: str | None
    insurer: str | None
    product_name: str | None


class ClassificationAnalysis(BaseModel):
    classification: str
    policy_count: int
    confirmed_total_count: int
    confirmed_total_amount: int
    indemnity_coverage_count: int
    excluded_coverage_count: int


class PortfolioAnalysisResponse(BaseModel):
    status: Literal["complete", "partial", "empty"]
    policy_count: int
    classification_count: int
    confirmed_total_count: int
    confirmed_total_amount: int
    indemnity_coverage_count: int
    excluded_coverage_count: int
    excluded_auto_policy_count: int
    age: int
    gender: str
    life_stage: str
    prepared_coverages: list[str]
    coverage_gaps: list[CoverageGap]
    baseline_notice: str
    classifications: list[ClassificationAnalysis]
    sources: list[AnalysisSource]
    notices: list[str]
