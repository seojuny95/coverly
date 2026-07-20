"""Deterministic portfolio-level facts for counsel."""

from pydantic import BaseModel

from app.modules.portfolio.premium import summarize_premiums
from app.modules.portfolio.schemas import (
    ActualLossCoverageItem,
    DeathBenefitGuideInput,
    EssentialCoverageItem,
    EssentialCoverageStatus,
    PolicyInput,
    PremiumOverview,
)
from app.modules.portfolio.summary import (
    duplicate_actual_loss_coverage_names,
    summarize_portfolio_coverages,
)


class PremiumFactBundle(BaseModel):
    monthly_total: int
    monthly_policy_count: int
    unconfirmed_policy_count: int
    note: str


class EssentialCoverageFact(BaseModel):
    kind: str
    label: str
    status: EssentialCoverageStatus
    status_label: str
    detail: str
    confirmed_amount: int | None
    coverage_count: int
    matched_coverage_names: list[str]
    coverage_group_notes: list[str]


class ActualLossDuplicateFact(BaseModel):
    has_duplicates: bool
    duplicate_coverage_names: list[str]
    review_note: str
    coverages: list[ActualLossCoverageItem]


class PortfolioFactBundle(BaseModel):
    premium: PremiumFactBundle
    essential_coverages: list[EssentialCoverageFact]
    actual_loss_duplicates: ActualLossDuplicateFact
    interpretation_rules: list[str]


def build_portfolio_fact_bundle(
    policies: list[PolicyInput],
    death_benefit_context: DeathBenefitGuideInput | None = None,
) -> PortfolioFactBundle:
    """Return a compact, LLM-friendly bundle of safe portfolio facts."""

    coverage_summary = summarize_portfolio_coverages(
        policies,
        death_benefit_context=death_benefit_context,
    )
    premium = summarize_premiums(policies)
    duplicates = duplicate_actual_loss_coverage_names(coverage_summary)

    return PortfolioFactBundle(
        premium=_premium_bundle(premium),
        essential_coverages=[
            _essential_coverage_fact(item)
            for item in coverage_summary.essential_coverage_check.items
        ],
        actual_loss_duplicates=ActualLossDuplicateFact(
            has_duplicates=bool(duplicates),
            duplicate_coverage_names=duplicates,
            review_note=(
                "실손형 보장이 여러 계약에서 확인돼요. 실제 중복 보상 여부와 유지 필요성은 "
                "각 계약 약관과 보험료를 함께 확인해야 해요."
                if duplicates
                else "현재 자료에서는 여러 계약에 걸친 실손형 중복 신호를 확인하지 못했어요."
            ),
            coverages=coverage_summary.actual_loss_coverages,
        ),
        interpretation_rules=[
            "확인된 사실과 확인이 필요한 항목을 나눠 말합니다.",
            "충분하거나 부족하다고 단정하지 않습니다.",
            "가입, 해지, 증액을 권유하지 않습니다.",
            "실제 지급 여부는 약관의 지급 조건과 면책 조건에 따라 달라질 수 있다고 안내합니다.",
        ],
    )


def _premium_bundle(premium: PremiumOverview) -> PremiumFactBundle:
    if premium.unconfirmed_policy_count:
        note = (
            "월납으로 확인된 보험료만 합산했어요. 납입주기나 금액이 확인되지 않은 보험은 "
            "월 합계에 포함하지 않았어요."
        )
    else:
        note = "월납으로 확인된 보험료를 합산했어요."
    return PremiumFactBundle(
        monthly_total=premium.monthly_total,
        monthly_policy_count=premium.monthly_policy_count,
        unconfirmed_policy_count=premium.unconfirmed_policy_count,
        note=note,
    )


def _essential_coverage_fact(item: EssentialCoverageItem) -> EssentialCoverageFact:
    return EssentialCoverageFact(
        kind=item.kind,
        label=item.label,
        status=item.status,
        status_label=_status_label(item.status),
        detail=item.detail,
        confirmed_amount=item.confirmed_amount,
        coverage_count=item.coverage_count,
        matched_coverage_names=item.matched_coverage_names,
        coverage_group_notes=[
            f"{group.label}: {group.detail}"
            for group in item.coverage_groups
            if group.coverage_names
        ],
    )


def _status_label(status: EssentialCoverageStatus) -> str:
    if status == "well_prepared":
        return "확인됨"
    if status == "needs_review":
        return "확인 필요"
    return "현재 자료에서 미확인"
