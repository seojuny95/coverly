"""Deterministic all-policy checks for the insurance analysis tab."""

from collections.abc import Callable

from app.modules.coverage.indemnity import classify_indemnity
from app.modules.portfolio.amounts import normalize, parse_amount
from app.modules.portfolio.death_benefit_guides import (
    DeathBenefitContext,
    death_benefit_guide,
)
from app.modules.portfolio.death_coverage import build_death_coverage_item
from app.modules.portfolio.essential_guides import (
    EssentialCoverageGuide,
    essential_coverage_guides,
)
from app.modules.portfolio.schemas import (
    CoverageInput,
    DeathBenefitGuideInput,
    EssentialCoverageCheck,
    EssentialCoverageItem,
    EssentialCoverageKind,
    EssentialCoverageStatus,
    PolicyInput,
    ReferenceSource,
)

_CANCER_TERMS = ("암", "악성신생물")
_CEREBROVASCULAR_TERMS = ("뇌혈관질환",)
_HEART_TERMS = ("심장질환", "심질환", "허혈성심")


def build_essential_coverage_check(
    policies: list[PolicyInput],
    death_benefit_context: DeathBenefitGuideInput | None = None,
) -> EssentialCoverageCheck:
    """Check uploaded policies without excluding any insurance category."""

    guides = essential_coverage_guides()
    death_guide = death_benefit_guide(_death_benefit_context(death_benefit_context))
    return EssentialCoverageCheck(
        items=[
            build_death_coverage_item(
                policies,
                guide=guides["death"],
                death_guide=death_guide,
            ),
            _fixed_coverage_item(
                policies,
                guide=guides["cancer"],
                kind="cancer",
                label="암 진단비",
                matches=lambda name: "진단" in name and any(term in name for term in _CANCER_TERMS),
                confirmed_detail=(
                    "일반암·유사암·고액암·소액암을 포함해 확인된 암 진단비를 모았어요."
                ),
            ),
            _fixed_coverage_item(
                policies,
                guide=guides["cerebrovascular"],
                kind="cerebrovascular",
                label="뇌혈관질환 진단비",
                matches=lambda name: (
                    "진단" in name and any(term in name for term in _CEREBROVASCULAR_TERMS)
                ),
                confirmed_detail="뇌혈관질환 진단비가 확인돼요.",
            ),
            _fixed_coverage_item(
                policies,
                guide=guides["ischemic_heart"],
                kind="ischemic_heart",
                label="심장질환 진단비",
                matches=lambda name: "진단" in name and any(term in name for term in _HEART_TERMS),
                confirmed_detail="심장질환·심질환 진단비가 확인돼요.",
            ),
            _medical_indemnity_item(policies, guides["medical_indemnity"]),
        ]
    )


def _fixed_coverage_item(
    policies: list[PolicyInput],
    *,
    guide: EssentialCoverageGuide,
    kind: EssentialCoverageKind,
    label: str,
    matches: Callable[[str], bool],
    confirmed_detail: str,
    reference_min_amount: int | None = None,
    reference_max_amount: int | None = None,
    reference_basis: str | None = None,
    reference_sources: list[ReferenceSource] | None = None,
    reference_amount_label: str | None = None,
    guidance_situation: str | None = None,
    guidance_reason: str | None = None,
) -> EssentialCoverageItem:
    matched = [
        coverage
        for policy in policies
        for coverage in policy.보장목록
        if matches(normalize(coverage.담보명))
    ]
    amounts = [amount for coverage in matched if (amount := parse_amount(coverage)) is not None]
    amount = sum(amounts) if amounts else None

    if matched:
        status: EssentialCoverageStatus = "well_prepared"
        detail = confirmed_detail
    else:
        status = "not_found"
        detail = "현재 올린 전체 보험에서는 확인하지 못했어요."

    return EssentialCoverageItem(
        kind=kind,
        label=label,
        status=status,
        confirmed_amount=amount,
        reference_min_amount=(
            guide.reference_min_amount if reference_min_amount is None else reference_min_amount
        ),
        reference_max_amount=(
            guide.reference_max_amount if reference_max_amount is None else reference_max_amount
        ),
        reference_basis=guide.basis if reference_basis is None else reference_basis,
        reference_sources=list(guide.sources) if reference_sources is None else reference_sources,
        reference_amount_label=reference_amount_label,
        guidance_situation=guidance_situation,
        guidance_reason=guidance_reason,
        coverage_count=len(matched),
        detail=detail,
        matched_coverage_names=sorted({coverage.담보명 for coverage in matched}),
    )


def _death_benefit_context(
    context: DeathBenefitGuideInput | None,
) -> DeathBenefitContext:
    if context is None:
        return DeathBenefitContext()
    return DeathBenefitContext(
        has_dependent_family=context.has_dependent_family,
        has_minor_children=context.has_minor_children,
        has_major_debt=context.has_major_debt,
    )


def _medical_indemnity_item(
    policies: list[PolicyInput],
    guide: EssentialCoverageGuide,
) -> EssentialCoverageItem:
    coverages = [
        (contract_index, coverage)
        for contract_index, policy in enumerate(policies)
        for coverage in policy.보장목록
        if _is_medical_indemnity_coverage(coverage, policy)
    ]
    has_multiple_contracts = len({contract_index for contract_index, _ in coverages}) > 1

    if coverages and not has_multiple_contracts:
        status: EssentialCoverageStatus = "well_prepared"
        detail = "실손의료보험 가입 사실이 확인돼요."
    elif coverages:
        status = "needs_review"
        detail = "실손의료보험이 여러 계약에서 확인돼요. 중복 가입 여부를 확인해보세요."
    else:
        status = "not_found"
        detail = "현재 올린 전체 보험에서는 실손의료보험을 확인하지 못했어요."

    return EssentialCoverageItem(
        kind="medical_indemnity",
        label="실손의료보험",
        status=status,
        reference_basis=guide.basis,
        reference_sources=list(guide.sources),
        coverage_count=len(coverages),
        detail=detail,
        matched_coverage_names=sorted({coverage.담보명 for _, coverage in coverages}),
    )


def _is_medical_indemnity_coverage(coverage: CoverageInput, policy: PolicyInput) -> bool:
    return classify_indemnity(coverage, policy=policy).medical_indemnity_status == "confirmed"
