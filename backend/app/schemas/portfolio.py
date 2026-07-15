"""Typed contracts for deterministic portfolio calculations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CoverageInput(BaseModel):
    """Coverage fields accepted from the current and extended parse response."""

    model_config = ConfigDict(extra="ignore")

    담보명: str
    가입금액: str = ""
    보장내용: str | None = None
    해설: str | None = None
    지급유형: str | None = None
    가입금액숫자: int | None = Field(default=None, ge=0)
    보장분류: str | None = None
    유형: str | None = None


class PolicyInsuredDemographicsInput(BaseModel):
    """Server-extracted demographics carried inside a parsed policy."""

    model_config = ConfigDict(extra="ignore")

    나이: int = Field(ge=0, le=120, strict=True)
    성별: Literal["남성", "여성"]
    생애단계: Literal["어린이", "성인", "시니어"]

    @model_validator(mode="after")
    def validate_life_stage(self) -> "PolicyInsuredDemographicsInput":
        expected = "어린이" if self.나이 < 19 else "시니어" if self.나이 >= 65 else "성인"
        if self.생애단계 != expected:
            raise ValueError("피보험자 생애단계가 나이와 일치하지 않습니다")
        return self


class PremiumInput(BaseModel):
    """Policy-level premium as carried by the parse result."""

    model_config = ConfigDict(extra="ignore")

    금액: int | None = Field(default=None, ge=0)
    납입주기: str | None = None


class PolicyInfoInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    보험사: str | None = None
    상품명: str | None = None
    보험분류: str | None = None
    상품태그: list[str] = Field(default_factory=list)
    피보험자정보: PolicyInsuredDemographicsInput | None = None
    보험료: PremiumInput | None = None


class PolicyInput(BaseModel):
    """One stored parse result; unknown upload metadata is intentionally allowed."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    기본정보: PolicyInfoInput
    보장목록: list[CoverageInput] = Field(default_factory=list)
    분석상태: str | None = None
    문서세션ID: str | None = None


class PortfolioSummaryRequest(BaseModel):
    policies: list[PolicyInput] = Field(default_factory=list)


class CoverageSourceItem(BaseModel):
    policy_id: str | None
    insurer: str | None
    product_name: str | None
    coverage_name: str
    amount: int
    original_amount: str


class CoverageTotalItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    normalized_name: str = Field(serialization_alias="normalizedName")
    display_name: str = Field(serialization_alias="category")
    major_category: str = Field(serialization_alias="majorCategory")
    total_amount: int = Field(serialization_alias="totalAmount")
    coverage_count: int = Field(serialization_alias="coverageCount")
    composition: list[CoverageSourceItem]


class IndemnityItem(BaseModel):
    policy_id: str | None
    insurer: str | None
    product_name: str | None
    coverage_name: str
    normalized_name: str
    cross_insurer_duplicate: bool
    original_amount: str = ""
    major_category: str = "기타"


class ExcludedCoverageItem(BaseModel):
    policy_id: str | None
    coverage_name: str
    original_amount: str
    reason: str
    insurer: str | None = None
    product_name: str | None = None
    major_category: str = "기타"


class DamageCoverageItem(BaseModel):
    coverage_name: str
    original_amount: str
    major_category: str = "기타"


class DamagePolicyCoverageGroup(BaseModel):
    policy_id: str | None
    insurer: str | None = None
    product_name: str | None = None
    coverages: list[DamageCoverageItem]


class DamageCoverageGroup(BaseModel):
    insurance_type: str
    policies: list[DamagePolicyCoverageGroup]


class PortfolioCoverageSummary(BaseModel):
    totals: list[CoverageTotalItem]
    indemnity_coverages: list[IndemnityItem]
    excluded_coverages: list[ExcludedCoverageItem]
    damage_coverages: list[DamageCoverageGroup] = Field(default_factory=list)
    excluded_auto_policy_count: int
