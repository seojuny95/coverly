"""Deterministic all-policy checks for the insurance analysis tab."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.modules.coverage.indemnity import classify_indemnity
from app.modules.portfolio.death_benefit_guides import (
    DeathBenefitContext,
    DeathBenefitGuide,
    death_benefit_guide,
)
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
    SpecialCoverageCheck,
    SpecialPolicyAnalysis,
    SpecialPolicyKind,
)

_UNITS = {
    "원": 1,
    "천원": 1_000,
    "만원": 10_000,
    "백만원": 1_000_000,
    "천만원": 10_000_000,
    "억원": 100_000_000,
}

_CANCER_TERMS = ("암", "악성신생물")
_CEREBROVASCULAR_TERMS = ("뇌혈관질환",)
_HEART_TERMS = ("심장질환", "심질환", "허혈성심")
_PRIMARY_DEATH_TERMS = (
    "일반사망",
    "질병사망",
    "사망보험금",
    "종신사망",
    "정기사망",
)
_ACCIDENT_DEATH_TERMS = ("상해", "재해")
_LIMITED_DEATH_TERMS = (
    "교통",
    "대중교통",
    "고속도로",
    "항공",
    "항공기",
    "선박",
    "열차",
    "전철",
    "지하철",
    "택시",
    "버스",
)
_SPECIAL_POLICY_LABELS: dict[SpecialPolicyKind, str] = {
    "auto": "자동차보험",
    "driver": "운전자보험",
    "travel": "여행자보험",
    "fire": "화재보험",
}

_AUTO_POLICY_COVERAGE_TERMS = (
    "대인배상",
    "대물배상",
    "자기차량손해",
    "자기차량",
    "자차",
    "자기신체사고",
    "자동차상해",
    "무보험자동차",
    "무보험차상해",
    "무보험차에의한상해",
)
_AUTO_PRODUCT_TERMS = (
    "자동차보험",
    "개인용자동차",
    "업무용자동차",
    "영업용자동차",
    "다이렉트자동차",
    "하이카",
)
_FIRE_PRODUCT_TERMS = (
    "화재보험",
    "주택화재보험",
    "주택종합보험",
    "재물보험",
)

_SPECIAL_COVERAGE_RULES: dict[SpecialPolicyKind, tuple[tuple[str, tuple[str, ...], str], ...]] = {
    "auto": (
        (
            "상대방의 신체 피해",
            ("대인배상",),
            "사고로 다른 사람이 다치거나 사망했을 때의 배상 담보예요.",
        ),
        (
            "상대방의 재물 피해",
            ("대물배상",),
            "사고로 다른 사람의 차량이나 재물에 생긴 손해를 배상하는 담보예요.",
        ),
        (
            "운전자·탑승자 상해",
            ("자동차상해", "자기신체사고", "자손"),
            "운전자나 탑승자가 다쳤을 때를 위한 담보예요.",
        ),
        ("내 차량 손해", ("자기차량손해", "자차"), "가입 차량에 생긴 손해를 위한 담보예요."),
        (
            "무보험차 사고 상해",
            ("무보험자동차", "무보험차상해", "무보험차에의한상해"),
            "무보험 차량과의 사고로 다쳤을 때를 위한 담보예요.",
        ),
    ),
    "driver": (
        (
            "교통사고 처리 지원",
            ("교통사고처리지원금", "형사합의"),
            "형사합의가 필요한 교통사고의 비용 부담을 위한 담보예요.",
        ),
        (
            "변호사 선임 비용",
            ("변호사선임", "변호사비용"),
            "교통사고 형사 절차에서 변호사를 선임할 때를 위한 담보예요.",
        ),
        ("운전자 벌금", ("벌금",), "교통사고로 확정된 벌금 비용을 위한 담보예요."),
    ),
    "travel": (
        (
            "해외 의료비",
            ("해외의료비", "해외실손의료비", "국외의료비"),
            "여행 중 질병이나 상해로 해외에서 지출한 의료비를 위한 담보예요.",
        ),
        (
            "휴대품 손해",
            ("휴대품손해", "휴대품"),
            "여행 중 휴대품의 도난이나 파손을 위한 담보예요.",
        ),
        (
            "여행 중 배상책임",
            ("배상책임",),
            "여행 중 다른 사람이나 재물에 입힌 손해를 위한 담보예요.",
        ),
        (
            "항공기 지연·여행 취소",
            ("항공기지연", "항공편지연", "여행취소", "출발지연"),
            "항공편 지연이나 여행 취소로 생긴 약정 비용을 위한 담보예요.",
        ),
    ),
    "fire": (
        (
            "건물·가재 화재 손해",
            ("화재손해", "건물화재", "가재화재", "주택화재"),
            "화재로 건물이나 가재도구에 생긴 직접 손해를 위한 담보예요.",
        ),
        (
            "화재 배상책임",
            ("화재배상책임", "화재대물배상", "화재대인배상", "폭발포함배상책임"),
            "화재로 다른 사람이나 재물에 입힌 손해를 위한 담보예요.",
        ),
        (
            "임시 거주·복구 비용",
            ("임시거주", "잔존물제거", "화재복구", "복구비용"),
            "화재 뒤 임시 거주나 잔존물 제거·복구 비용을 위한 담보예요.",
        ),
    ),
}


@dataclass(frozen=True)
class _SpecialPolicyMatch:
    kind: SpecialPolicyKind
    reason: str


DeathCoverageKind = Literal["primary", "accident", "limited"]


@dataclass(frozen=True)
class _DeathCoverageMatch:
    coverage: CoverageInput
    kind: DeathCoverageKind


def build_essential_coverage_check(
    policies: list[PolicyInput],
    death_benefit_context: DeathBenefitGuideInput | None = None,
) -> EssentialCoverageCheck:
    """Check uploaded policies without excluding any insurance category."""

    guides = essential_coverage_guides()
    death_guide = death_benefit_guide(_death_benefit_context(death_benefit_context))
    return EssentialCoverageCheck(
        items=[
            _death_coverage_item(
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


def build_special_policy_analyses(policies: list[PolicyInput]) -> list[SpecialPolicyAnalysis]:
    """Return analyses only for special policy types actually present."""

    grouped: dict[SpecialPolicyKind, list[PolicyInput]] = {
        "auto": [],
        "driver": [],
        "travel": [],
        "fire": [],
    }
    for policy in policies:
        for match in _special_policy_matches(policy):
            grouped[match.kind].append(policy)

    analyses: list[SpecialPolicyAnalysis] = []
    ordered_kinds: tuple[SpecialPolicyKind, ...] = (
        "auto",
        "driver",
        "travel",
        "fire",
    )
    for kind in ordered_kinds:
        matched = grouped[kind]
        if not matched:
            continue
        product_names = sorted({policy.기본정보.상품명 or "상품명 미확인" for policy in matched})
        coverage_names = sorted(
            {
                coverage.담보명
                for policy in matched
                for coverage in policy.보장목록
                if coverage.담보명.strip()
            }
        )
        coverage_checks = _build_special_coverage_checks(kind, coverage_names)
        classification_reasons = _classification_reasons_for(kind, matched)
        analyses.append(
            SpecialPolicyAnalysis(
                kind=kind,
                label=_SPECIAL_POLICY_LABELS[kind],
                policy_count=len(matched),
                product_names=product_names,
                confirmed_coverage_names=coverage_names,
                classification_reasons=classification_reasons,
                overview=_special_policy_overview(coverage_checks),
                coverage_checks=coverage_checks,
            )
        )
    return analyses


def _build_special_coverage_checks(
    kind: SpecialPolicyKind, coverage_names: list[str]
) -> list[SpecialCoverageCheck]:
    checks: list[SpecialCoverageCheck] = []
    for label, terms, detail in _SPECIAL_COVERAGE_RULES[kind]:
        normalized_terms = tuple(_normalize(term) for term in terms)
        matched_names = [
            name
            for name in coverage_names
            if any(term in _normalize(name) for term in normalized_terms)
        ]
        checks.append(
            SpecialCoverageCheck(
                label=label,
                status="confirmed" if matched_names else "not_found",
                detail=detail,
                matched_coverage_names=matched_names,
            )
        )
    return checks


def _special_policy_overview(checks: list[SpecialCoverageCheck]) -> str:
    confirmed = [check.label for check in checks if check.status == "confirmed"]
    missing = [check.label for check in checks if check.status == "not_found"]
    if not confirmed:
        return (
            "담보명은 확인됐지만 주요 보장 영역과 연결되는 항목은 현재 자료에서 "
            "찾지 못했어요. 실제 가입 여부는 증권 원문을 더 확인해야 해요."
        )
    if not missing:
        return (
            f"{', '.join(confirmed)}이 모두 확인돼요. 다만 지급 범위와 한도, "
            "면책 조건은 각 증권과 약관을 더 확인해야 해요."
        )
    return (
        f"{', '.join(confirmed)}은 확인돼요. {', '.join(missing)}은 현재 자료에서 "
        "찾지 못했으며, 이것만으로 미가입이라고 단정할 수는 없어요."
    )


def _death_coverage_item(
    policies: list[PolicyInput],
    *,
    guide: EssentialCoverageGuide,
    death_guide: DeathBenefitGuide,
) -> EssentialCoverageItem:
    matches = [
        _DeathCoverageMatch(coverage=coverage, kind=kind)
        for policy in policies
        for coverage in policy.보장목록
        if (kind := _death_coverage_kind(_normalize(coverage.담보명))) is not None
    ]
    primary_coverages = [match.coverage for match in matches if match.kind == "primary"]
    primary_amounts = [
        amount for coverage in primary_coverages if (amount := _parse_amount(coverage)) is not None
    ]
    primary_amount = sum(primary_amounts) if primary_amounts else None
    status, detail = _death_coverage_status_detail(matches)

    return EssentialCoverageItem(
        kind="death",
        label="사망 보장",
        status=status,
        confirmed_amount=primary_amount,
        reference_min_amount=death_guide.min_amount,
        reference_max_amount=death_guide.max_amount,
        reference_basis=death_guide.reason or guide.basis,
        reference_sources=list(death_guide.sources),
        reference_amount_label=death_guide.amount_label,
        guidance_situation=death_guide.situation,
        guidance_reason=death_guide.reason,
        coverage_count=len(matches),
        detail=detail,
        matched_coverage_names=sorted({match.coverage.담보명 for match in matches}),
        coverage_groups=_death_coverage_groups(matches),
    )


def _death_coverage_kind(name: str) -> DeathCoverageKind | None:
    if "사망" not in name:
        return None
    if any(term in name for term in _normalized_terms(_LIMITED_DEATH_TERMS)):
        return "limited"
    if any(term in name for term in _normalized_terms(_ACCIDENT_DEATH_TERMS)):
        return "accident"
    if any(term in name for term in _normalized_terms(_PRIMARY_DEATH_TERMS)):
        return "primary"
    return "primary"


def _death_coverage_status_detail(
    matches: list[_DeathCoverageMatch],
) -> tuple[EssentialCoverageStatus, str]:
    if not matches:
        return "not_found", "현재 올린 전체 보험에서는 사망 담보를 확인하지 못했어요."
    if any(match.kind == "primary" for match in matches):
        return "well_prepared", "기본 사망 보장이 확인돼요."
    if any(match.kind == "accident" for match in matches):
        return (
            "needs_review",
            "상해 중심 사망 담보가 보여요. "
            "질병·일반 사망까지 보는 기본 사망보험과는 범위가 달라요.",
        )
    return (
        "needs_review",
        "제한적인 사망 담보만 보여요. "
        "가족 생활비 목적의 사망보험으로 충분한지는 따로 확인해보세요.",
    )


def _death_coverage_groups(matches: list[_DeathCoverageMatch]) -> list[CoverageGroup]:
    group_specs: tuple[tuple[DeathCoverageKind, str, CoverageGroupTone, str], ...] = (
        (
            "primary",
            "기본 사망 보장",
            "confirmed",
            "일반사망·질병사망처럼 가족 생활비 목적의 사망보험 판단에 반영하는 담보예요.",
        ),
        (
            "accident",
            "상해 중심 사망 담보",
            "review",
            "상해나 재해로 인한 사망은 확인되지만, "
            "질병·일반 사망까지 보는 기본 사망보험과는 범위가 달라요.",
        ),
        (
            "limited",
            "제한적인 사망 담보",
            "limited",
            "교통·대중교통·고속도로처럼 특정 사고 조건에 묶인 사망 담보예요.",
        ),
    )
    groups: list[CoverageGroup] = []
    for kind, label, tone, detail in group_specs:
        names = sorted({match.coverage.담보명 for match in matches if match.kind == kind})
        if not names:
            continue
        groups.append(
            CoverageGroup(
                label=label,
                tone=tone,
                detail=detail,
                coverage_names=names,
            )
        )
    return groups


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
        if matches(_normalize(coverage.담보명))
    ]
    amounts = [amount for coverage in matched if (amount := _parse_amount(coverage)) is not None]
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


def _special_policy_matches(policy: PolicyInput) -> tuple[_SpecialPolicyMatch, ...]:
    category = _normalize(policy.기본정보.보험분류 or "")
    product = _normalize(policy.기본정보.상품명 or "")
    tags = tuple(_normalize(tag) for tag in _product_tags(policy))
    tags_text = " ".join(tags)
    identity = f"{category} {product} {tags_text}"
    coverage_names = [_normalize(coverage.담보명) for coverage in policy.보장목록]

    matches: list[_SpecialPolicyMatch] = []
    if (
        _normalize("자동차보험") in category
        or any(term in product for term in _normalized_terms(_AUTO_PRODUCT_TERMS))
        or any(_normalize("자동차") in tag or _normalize("자동차보험") in tag for tag in tags)
    ):
        matches.append(
            _SpecialPolicyMatch(
                "auto",
                "보험분류, 상품명 또는 상품태그에서 자동차보험 성격이 확인돼요.",
            )
        )
    elif _has_auto_policy_coverages(category, tags, coverage_names):
        matches.append(
            _SpecialPolicyMatch(
                "auto",
                "손해보험 증권 안에서 대인배상, 대물배상, 자차처럼 자동차보험 담보명이 확인돼요.",
            )
        )
    if "운전자" in identity and _is_damage_policy_identity(category, tags):
        matches.append(
            _SpecialPolicyMatch(
                "driver",
                "손해보험 증권 안에서 운전자보험 상품명 또는 태그가 확인돼요.",
            )
        )
    if (
        "여행자" in identity or "여행보험" in identity or "해외여행" in identity
    ) and _is_damage_policy_identity(category, tags):
        matches.append(
            _SpecialPolicyMatch(
                "travel",
                "손해보험 증권 안에서 여행자보험 상품명 또는 태그가 확인돼요.",
            )
        )
    if _is_fire_policy(category, product, tags, coverage_names):
        matches.append(
            _SpecialPolicyMatch(
                "fire",
                "손해보험 증권 안에서 화재, 주택, 재물 손해 관련 상품명이나 담보명이 확인돼요.",
            )
        )
    return tuple(dict.fromkeys(matches))


def _has_auto_policy_coverages(
    category: str,
    tags: tuple[str, ...],
    coverage_names: list[str],
) -> bool:
    """Infer auto insurance from auto-policy-specific coverage names only.

    Driver policies often contain words like "자동차사고" in fine/legal-cost
    coverages, so this intentionally uses mandatory/typical auto insurance
    coverage names instead of the broad word "자동차".
    """

    if not _is_damage_policy_identity(category, tags):
        return False
    terms = tuple(_normalize(term) for term in _AUTO_POLICY_COVERAGE_TERMS)
    return any(any(term in name for term in terms) for name in coverage_names)


def _is_fire_policy(
    category: str,
    product: str,
    tags: tuple[str, ...],
    coverage_names: list[str],
) -> bool:
    if category in {_normalize("화재보험"), _normalize("주택화재보험")}:
        return True
    if any(tag in {_normalize("화재보험"), _normalize("주택화재보험")} for tag in tags):
        return True
    if any(term in product for term in _normalized_terms(_FIRE_PRODUCT_TERMS)):
        return True
    if not _is_damage_policy_identity(category, tags):
        return False
    fire_terms = tuple(
        _normalize(term)
        for _label, terms, _detail in _SPECIAL_COVERAGE_RULES["fire"]
        for term in terms
    )
    return any(any(term in name for term in fire_terms) for name in coverage_names)


def _classification_reasons_for(kind: SpecialPolicyKind, policies: list[PolicyInput]) -> list[str]:
    reasons = [
        match.reason
        for policy in policies
        for match in _special_policy_matches(policy)
        if match.kind == kind
    ]
    return list(dict.fromkeys(reasons))


def _normalized_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_normalize(term) for term in terms)


def _is_damage_policy_identity(category: str, tags: tuple[str, ...]) -> bool:
    damage_categories = {
        _normalize("손해보험"),
        _normalize("자동차보험"),
        _normalize("운전자보험"),
        _normalize("운전자상해보험"),
        _normalize("여행자보험"),
        _normalize("화재보험"),
        _normalize("주택화재보험"),
        _normalize("배상책임보험"),
        _normalize("보증보험"),
    }
    damage_tags = {
        _normalize("자동차보험"),
        _normalize("운전자보험"),
        _normalize("여행자보험"),
        _normalize("화재보험"),
        _normalize("주택화재보험"),
        _normalize("배상책임보험"),
        _normalize("보증보험"),
    }
    return category in damage_categories or any(tag in damage_tags for tag in tags)


def _product_tags(policy: PolicyInput) -> list[str]:
    tags = policy.기본정보.상품태그
    if not isinstance(tags, list):
        return []
    return [tag for tag in tags if isinstance(tag, str)]


def _parse_amount(coverage: CoverageInput) -> int | None:
    if coverage.가입금액숫자 is not None:
        return coverage.가입금액숫자
    compact = re.sub(r"\s+", "", coverage.가입금액).replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(억원|천만원|백만원|만원|천원|원)", compact)
    if match is None:
        return None
    amount = float(match.group(1)) * _UNITS[match.group(2)]
    return int(amount) if amount.is_integer() else None


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()
