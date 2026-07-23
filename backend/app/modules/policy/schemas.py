"""HTTP contracts for policy parsing."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.grounding import AMOUNT_UNVERIFIED
from app.modules.policy.models import (
    AmountVerificationStatus,
    CoverageExplanationBasis,
    CoveragePeriod,
    CoverageType,
    InsuredDemographics,
    PolicyAnalysisStatus,
    PolicyClassificationName,
    PolicyTermsStatus,
    PremiumSummary,
    VehicleInfo,
)


class Coverage(BaseModel):
    """Public coverage contract with explicit verification and row type state."""

    담보명: str
    가입금액: str
    가입금액상태: AmountVerificationStatus
    보장내용: str | None
    해설: str | None
    설명근거: CoverageExplanationBasis
    유형: CoverageType

    @model_validator(mode="before")
    @classmethod
    def populate_explicit_states(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        coverage = dict(value)
        coverage_type = coverage.get("유형", "담보")
        amount = coverage.get("가입금액", "")
        coverage["유형"] = coverage_type
        if coverage.get("보장내용"):
            coverage["설명근거"] = "policy_wording"
        elif coverage.get("해설"):
            coverage["설명근거"] = "generated_guidance"
        else:
            coverage["설명근거"] = "none"
        if "가입금액상태" not in coverage:
            if coverage_type == "부가":
                coverage["가입금액상태"] = "not_applicable"
            elif not amount or amount == AMOUNT_UNVERIFIED:
                coverage["가입금액상태"] = "needs_review"
            else:
                coverage["가입금액상태"] = "confirmed"
        return coverage


class PolicySummary(BaseModel):
    """Public policy summary with canonical classification metadata."""

    보험분류: PolicyClassificationName
    상품태그: list[str]
    보험사: str | None = None
    상품명: str | None = None
    증권번호: str | None = None
    계약자: str | None = None
    피보험자: str | None = None
    보험기간: CoveragePeriod | None = None
    만기일: str | None = None
    납입기간: str | None = None
    보험료: PremiumSummary | None = None
    피보험자정보: InsuredDemographics | None = None
    차량정보: VehicleInfo | None = None


class PolicyParseResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: Literal["accepted"]
    document_id: UUID = Field(serialization_alias="documentId")
    문자수: int = Field(ge=0)
    기본정보: PolicySummary
    보장목록: list[Coverage]
    분석상태: PolicyAnalysisStatus
    policy_terms_status: PolicyTermsStatus = "unavailable"
