"""API contracts for deterministic portfolio analysis."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.portfolio import PolicyInput


class PortfolioAnalysisRequest(BaseModel):
    policies: list[PolicyInput] = Field(default_factory=list)


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
    classifications: list[ClassificationAnalysis]
    sources: list[AnalysisSource]
    notices: list[str]
