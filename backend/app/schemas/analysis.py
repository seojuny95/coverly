"""API contracts for grounded portfolio analysis."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.consultation import (
    ConsultationEvidence,
    DemographicSource,
    Gender,
    GenerationMode,
    InsuredDemographics,
)
from app.schemas.portfolio import ExcludedCoverageItem, PolicyInput


class AnalysisContextAnswer(BaseModel):
    question: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=500)


class PortfolioAnalysisRequest(BaseModel):
    policies: list[PolicyInput] = Field(default_factory=list)
    demographics: InsuredDemographics | None = None
    personal_context: list[AnalysisContextAnswer] = Field(default_factory=list, max_length=6)
    # Temporary compatibility fields for the current client. New clients send demographics.
    age: int | None = Field(default=None, ge=0, le=120)
    gender: Gender | None = None

    def resolved_demographics(self) -> InsuredDemographics:
        if self.demographics is not None:
            return self.demographics
        source: DemographicSource = (
            "user" if self.age is not None or self.gender is not None else "unknown"
        )
        return InsuredDemographics(
            age=self.age,
            gender=self.gender or "미상",
            source=source,
        )


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


class CounselorInsight(BaseModel):
    title: str
    detail: str
    evidence_ids: list[str]


AnalysisContextKind = Literal["소득", "치료·회복 기간 생활비", "부양 책임", "가용 예산"]


class AmountReviewItem(BaseModel):
    coverage_name: str
    current_amount: int
    title: str
    guidance: str
    rationale: str
    suggested_range: str | None = None
    confidence: Literal["low"] = "low"
    basis: Literal["general_guidance", "personal_context"] = "general_guidance"
    requires_personal_context: bool = True
    required_context: list[AnalysisContextKind]
    evidence_ids: list[str]


class CounselorAnalysis(BaseModel):
    overview: str
    strengths: list[CounselorInsight]
    gaps: list[CounselorInsight]
    amount_review_items: list[AmountReviewItem]
    next_questions: list[str]
    next_steps: list[str]


class PremiumPolicyItem(BaseModel):
    policy_id: str | None
    insurer: str | None
    product_name: str | None
    monthly_amount: int | None
    cycle: str | None


class PremiumOverview(BaseModel):
    monthly_total: int
    monthly_policy_count: int
    unconfirmed_policy_count: int
    items: list[PremiumPolicyItem]


class PremiumBenchmarkSource(BaseModel):
    label: str
    url: str
    published_at: str
    reliability: str
    caveat: str


class PremiumBenchmark(BaseModel):
    age_band_label: str
    min_age: int
    max_age: int
    average_monthly_premium: int
    source: PremiumBenchmarkSource


PriorityCheckKind = Literal["premium", "duplicate", "coverage_gap", "contract"]


class PriorityCheck(BaseModel):
    kind: PriorityCheckKind
    title: str
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


class CoverageAmountStatusItem(BaseModel):
    category: str
    amount: int
    coverage_count: int
    title: str
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


class CoverageAmountStatus(BaseModel):
    title: str
    detail: str
    confirmed_total_amount: int
    confirmed_category_count: int
    unconfirmed_coverage_count: int
    items: list[CoverageAmountStatusItem]


ClaimConditionKind = Literal["fixed", "indemnity", "contract"]


class ClaimConditionCheck(BaseModel):
    kind: ClaimConditionKind
    title: str
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


class PolicyChangeSource(BaseModel):
    label: str
    url: str
    published_at: str
    reliability: str
    caveat: str


class PolicyChangeCheck(BaseModel):
    title: str
    summary: str
    user_impact: str
    effective_from: str | None = None
    applies_to: str
    related_tags: list[str] = Field(default_factory=list, exclude=True)
    source: PolicyChangeSource


class PortfolioAnalysisResponse(BaseModel):
    status: Literal["complete", "partial", "empty"]
    policy_count: int
    classification_count: int
    confirmed_total_count: int
    indemnity_coverage_count: int
    indemnity_duplicate_count: int
    excluded_coverage_count: int
    excluded_coverages: list[ExcludedCoverageItem]
    excluded_auto_policy_count: int
    age: int | None
    gender: str
    life_stage: str
    demographics: InsuredDemographics
    prepared_coverages: list[str]
    coverage_gaps: list[CoverageGap]
    baseline_notice: str
    classifications: list[ClassificationAnalysis]
    sources: list[AnalysisSource]
    counselor: CounselorAnalysis
    evidence: list[ConsultationEvidence]
    notices: list[str]
    limitations: list[str]
    premium: PremiumOverview
    premium_benchmark: PremiumBenchmark | None = None
    priority_checks: list[PriorityCheck] = Field(default_factory=list, max_length=3)
    coverage_amount_status: CoverageAmountStatus
    claim_condition_checks: list[ClaimConditionCheck] = Field(default_factory=list)
    policy_change_checks: list[PolicyChangeCheck] = Field(default_factory=list)
    generation: GenerationMode
