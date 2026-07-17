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
    CoverageGroup,
    CoverageGroupTone,
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
_SPECIAL_CANCER_GROUPS = (
    (
        "similar",
        "유사암 진단비",
        "유사암 진단비가 가입되어 있어요.",
        ("유사암", "갑상선암", "기타피부암", "제자리암", "경계성종양"),
    ),
    (
        "high_value",
        "고액암 진단비",
        "고액암 진단비가 가입되어 있어요.",
        ("고액암", "고액치료비암", "특정고액암"),
    ),
    (
        "small",
        "소액암 진단비",
        "소액암 진단비가 가입되어 있어요.",
        ("소액암", "소액치료비암"),
    ),
)
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
                matches=_is_primary_cancer_diagnosis,
                confirmed_detail="암 진단비가 확인돼요.",
                coverage_groups=_cancer_coverage_groups(policies),
                # Keep every cancer group visible while comparing only primary cancer amounts.
                coverage_count_override=_cancer_coverage_count(policies),
                matched_coverage_names_override=_cancer_coverage_names(policies),
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
    coverage_groups: list[CoverageGroup] | None = None,
    coverage_count_override: int | None = None,
    matched_coverage_names_override: list[str] | None = None,
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
        coverage_count=len(matched) if coverage_count_override is None else coverage_count_override,
        detail=detail,
        matched_coverage_names=(
            sorted({coverage.담보명 for coverage in matched})
            if matched_coverage_names_override is None
            else matched_coverage_names_override
        ),
        coverage_groups=coverage_groups or [],
    )


def _is_cancer_diagnosis(name: str) -> bool:
    if "진단" not in name:
        return False
    if any(term in name for term in _CANCER_TERMS):
        return True
    return any(
        _has_group_term_before_diagnosis(name, terms)
        for _key, _label, _detail, terms in _SPECIAL_CANCER_GROUPS
    )


def _special_cancer_group_key(name: str) -> str | None:
    if not _is_cancer_diagnosis(name):
        return None
    for key, _label, _detail, terms in _SPECIAL_CANCER_GROUPS:
        if _has_group_term_before_diagnosis(name, terms):
            return key
    return None


def _has_group_term_before_diagnosis(name: str, terms: tuple[str, ...]) -> bool:
    diagnosis_prefix = name.partition("진단")[0]
    return any(term in diagnosis_prefix and f"{term}제외" not in diagnosis_prefix for term in terms)


def _is_primary_cancer_diagnosis(name: str) -> bool:
    return _is_cancer_diagnosis(name) and _special_cancer_group_key(name) is None


def _cancer_coverages(policies: list[PolicyInput]) -> list[CoverageInput]:
    return [
        coverage
        for policy in policies
        for coverage in policy.보장목록
        if _is_cancer_diagnosis(normalize(coverage.담보명))
    ]


def _cancer_coverage_names(policies: list[PolicyInput]) -> list[str]:
    return sorted({coverage.담보명 for coverage in _cancer_coverages(policies)})


def _cancer_coverage_count(policies: list[PolicyInput]) -> int:
    return len(_cancer_coverages(policies))


def _cancer_coverage_groups(policies: list[PolicyInput]) -> list[CoverageGroup]:
    coverages = _cancer_coverages(policies)
    groups: list[CoverageGroup] = []

    primary_coverages = [
        coverage
        for coverage in coverages
        if _special_cancer_group_key(normalize(coverage.담보명)) is None
    ]
    if primary_coverages:
        groups.append(
            _coverage_group(
                label="암 진단비",
                tone="confirmed",
                detail="현재 가입금액 기준에 반영하는 일반 암 진단비예요.",
                coverages=primary_coverages,
            )
        )

    for key, label, detail, _terms in _SPECIAL_CANCER_GROUPS:
        group_coverages = [
            coverage
            for coverage in coverages
            if _special_cancer_group_key(normalize(coverage.담보명)) == key
        ]
        if not group_coverages:
            continue
        groups.append(
            _coverage_group(
                label=label,
                tone="review",
                detail=detail,
                coverages=group_coverages,
            )
        )

    return groups


def _coverage_group(
    *,
    label: str,
    tone: CoverageGroupTone,
    detail: str,
    coverages: list[CoverageInput],
) -> CoverageGroup:
    amounts = [amount for coverage in coverages if (amount := parse_amount(coverage)) is not None]
    return CoverageGroup(
        label=label,
        tone=tone,
        detail=detail,
        coverage_names=sorted({coverage.담보명 for coverage in coverages}),
        total_amount=sum(amounts) if amounts else None,
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
