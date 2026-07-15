"""Deterministic, non-RAG portfolio coverage aggregation."""

import re
from collections import defaultdict
from dataclasses import dataclass

from app.modules.coverage.indemnity import (
    IndemnityClassification,
    PaymentBasis,
    classify_indemnity,
    has_negated_actual_loss_marker,
    is_damage_policy_context,
)
from app.modules.coverage.matching import (
    canonicalize_coverage_name,
    choose_display_name,
)
from app.modules.portfolio.essential_coverage import (
    build_essential_coverage_check,
    build_special_policy_analyses,
)
from app.modules.portfolio.premium import summarize_premiums
from app.modules.portfolio.schemas import (
    ActualLossCoverageItem,
    ClaimChannelBlock,
    CoverageInput,
    CoverageSourceItem,
    CoverageTotalItem,
    DamageCoverageGroup,
    DamageCoverageItem,
    DamagePolicyCoverageGroup,
    DeathBenefitGuideInput,
    EssentialCoverageCheck,
    ExcludedCoverageItem,
    PolicyInput,
    PortfolioCoverageSummary,
    PremiumBenchmark,
    PremiumOverview,
)
from app.modules.qa.claim_channels import claim_channel_block
from app.modules.reference_data.premium_benchmark import premium_benchmark_for_age

_AUTO_TAG_TERMS = ("자동차", "자동차보험")
_AUTO_COVERAGE_TERMS = (
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
_FIRE_COVERAGE_TERMS = (
    "화재손해",
    "건물화재",
    "가재화재",
    "주택화재",
    "화재배상책임",
    "화재대물배상",
    "화재대인배상",
    "폭발포함배상책임",
    "화재폭발",
)
_SAFE_FIXED_NAME_TERMS = (
    "진단비",
    "수술비",
    "입원일당",
    "입원비",
    "사망",
    "후유장해",
)
_UNCONFIRMED_PAYMENT_REASON = "지급 방식을 확인하지 못해 합계에는 더하지 않았어요."
_UNCONFIRMED_AMOUNT_REASON = "가입금액을 숫자로 확인하지 못해 합계에는 더하지 않았어요."
_UNCONFIRMED_NAME_REASON = "담보명을 분류하지 못해 합계에는 더하지 않았어요."
_ACTUAL_LOSS_EXCLUSION_REASON = "실손형 담보라 가입금액 합계에는 더하지 않았어요."
_UNITS = {
    "원": 1,
    "천원": 1_000,
    "만원": 10_000,
    "백만원": 1_000_000,
    "천만원": 10_000_000,
    "억원": 100_000_000,
}
MAJOR_CATEGORY_ORDER = (
    "사망",
    "후유장해",
    "진단",
    "수술",
    "치료",
    "기타",
)
_DAMAGE_INSURANCE_TYPE_ORDER = (
    "자동차보험",
    "운전자보험",
    "여행자보험",
    "화재보험",
    "배상책임보험",
    "보증보험",
    "손해보험",
)


@dataclass(frozen=True)
class PortfolioFacts:
    """Stable facts reusable by analysis and Q&A without introducing RAG."""

    policies: tuple[PolicyInput, ...]
    coverage_summary: PortfolioCoverageSummary


@dataclass(frozen=True)
class _ActualLossRow:
    contract_index: int
    policy: PolicyInput
    coverage: CoverageInput
    normalized_name: str
    classification: IndemnityClassification


def normalize_coverage_name(name: str) -> str:
    """Normalize formatting only, avoiding semantic aliases that can over-group."""

    return re.sub(r"[^0-9A-Za-z가-힣]", "", name).casefold()


def major_category(name: str) -> str:
    """Return a display-only group without changing coverage identity."""

    normalized = normalize_coverage_name(name)
    if "사망" in normalized:
        return "사망"
    if "후유장해" in normalized:
        return "후유장해"
    if "수술" in normalized:
        return "수술"
    if "진단" in normalized or "악성신생물" in normalized:
        return "진단"
    if (
        "치료" in normalized
        or "의료비" in normalized
        or "입원" in normalized
        or "통원" in normalized
    ):
        return "치료"
    return "기타"


def is_damage_policy(policy: PolicyInput) -> bool:
    """Return whether a policy belongs to the separately handled non-life branch."""

    return is_damage_policy_context(policy)


def is_auto_policy(policy: PolicyInput) -> bool:
    """Return whether a policy is an auto policy inside the damage branch."""

    return any(term in _damage_insurance_type(policy) for term in _AUTO_TAG_TERMS)


def _summary_payment_basis(
    coverage: CoverageInput,
    classification: IndemnityClassification,
) -> PaymentBasis:
    """Keep conservative fixed-benefit inference beside summary aggregation."""

    if classification.payment_basis != "unknown":
        return classification.payment_basis
    if coverage.지급유형:
        return "unknown"
    if has_negated_actual_loss_marker(coverage):
        return "unknown"
    if any(term in coverage.담보명 for term in _SAFE_FIXED_NAME_TERMS):
        return "fixed"
    return "unknown"


def _parse_amount(coverage: CoverageInput) -> int | None:
    if coverage.가입금액숫자 is not None:
        return coverage.가입금액숫자

    compact = re.sub(r"\s+", "", coverage.가입금액).replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(억원|천만원|백만원|만원|천원|원)", compact)
    if match is None:
        return None
    value = float(match.group(1))
    amount = value * _UNITS[match.group(2)]
    if not amount.is_integer():
        return None
    return int(amount)


def summarize_portfolio_coverages(
    policies: list[PolicyInput],
    death_benefit_context: DeathBenefitGuideInput | None = None,
) -> PortfolioCoverageSummary:
    """Aggregate only amounts whose fixed-benefit meaning and value are safe."""

    grouped_sources: dict[str, list[CoverageSourceItem]] = defaultdict(list)
    source_names_by_group: dict[str, list[str]] = defaultdict(list)
    actual_loss_rows: list[_ActualLossRow] = []
    excluded: list[ExcludedCoverageItem] = []
    damage_rows: dict[str, list[DamagePolicyCoverageGroup]] = defaultdict(list)
    auto_count = 0

    for contract_index, policy in enumerate(policies):
        classified_coverages = [
            (coverage, classify_indemnity(coverage, policy=policy)) for coverage in policy.보장목록
        ]
        for coverage, classification in classified_coverages:
            if classification.payment_basis != "indemnity":
                continue
            actual_loss_rows.append(
                _ActualLossRow(
                    contract_index=contract_index,
                    policy=policy,
                    coverage=coverage,
                    normalized_name=canonicalize_coverage_name(coverage.담보명).normalized_key,
                    classification=classification,
                )
            )

        if is_damage_policy(policy):
            damage_rows[_damage_insurance_type(policy)].append(_damage_policy_group(policy))
            if is_auto_policy(policy):
                auto_count += 1
            continue
        for coverage, classification in classified_coverages:
            group_key = canonicalize_coverage_name(coverage.담보명).normalized_key
            payment_basis = _summary_payment_basis(coverage, classification)
            if payment_basis == "indemnity":
                if classification.medical_indemnity_status != "confirmed":
                    excluded.append(_excluded(policy, coverage, _ACTUAL_LOSS_EXCLUSION_REASON))
                continue
            if payment_basis == "unknown":
                excluded.append(_excluded(policy, coverage, _UNCONFIRMED_PAYMENT_REASON))
                continue
            amount = _parse_amount(coverage)
            if amount is None:
                excluded.append(_excluded(policy, coverage, _UNCONFIRMED_AMOUNT_REASON))
                continue
            if not group_key:
                excluded.append(_excluded(policy, coverage, _UNCONFIRMED_NAME_REASON))
                continue
            source_names_by_group[group_key].append(coverage.담보명)
            grouped_sources[group_key].append(
                CoverageSourceItem(
                    policy_id=policy.id,
                    insurer=policy.기본정보.보험사,
                    product_name=policy.기본정보.상품명,
                    coverage_name=coverage.담보명,
                    amount=amount,
                    original_amount=coverage.가입금액,
                )
            )

    display_names = {
        group_key: choose_display_name(source_names)
        for group_key, source_names in source_names_by_group.items()
    }
    totals = _build_fixed_totals(grouped_sources, display_names)
    actual_loss_coverages = _build_actual_loss_items(actual_loss_rows)
    excluded.sort(
        key=lambda item: (
            item.policy_id or "",
            item.coverage_name,
            item.original_amount,
            item.reason,
        )
    )
    essential_coverage_check = build_essential_coverage_check(policies, death_benefit_context)
    summary = PortfolioCoverageSummary(
        totals=totals,
        actual_loss_coverages=actual_loss_coverages,
        excluded_coverages=excluded,
        damage_coverages=_build_damage_groups(damage_rows),
        excluded_auto_policy_count=auto_count,
    )
    return summary.model_copy(
        update={
            "essential_coverage_check": essential_coverage_check,
            "special_policy_analyses": build_special_policy_analyses(policies),
            "claim_channels": _claim_channels(policies, essential_coverage_check),
            "premium": PremiumOverview.model_validate(
                summarize_premiums(policies).model_dump(mode="python")
            ),
            "premium_benchmark": _premium_benchmark(policies),
        }
    )


def duplicate_actual_loss_coverage_names(
    summary: PortfolioCoverageSummary,
) -> list[str]:
    """Return actual-loss coverage names found in multiple contracts.

    This is a review signal, not a payout conclusion. Exact proportional
    compensation and overlap rules still depend on each policy's terms.
    """

    names_by_normalized_name: dict[str, str] = {}
    for item in summary.actual_loss_coverages:
        if not item.duplicate_across_contracts:
            continue
        key = item.normalized_name or item.coverage_name
        names_by_normalized_name.setdefault(key, item.coverage_name)
    return sorted(names_by_normalized_name.values())


def build_portfolio_facts(policies: list[PolicyInput]) -> PortfolioFacts:
    """Build the deterministic common input for summary, analysis, and Q&A."""

    return PortfolioFacts(
        policies=tuple(policy for policy in policies if not is_damage_policy(policy)),
        coverage_summary=summarize_portfolio_coverages(policies),
    )


def _claim_channels(
    policies: list[PolicyInput],
    essential_coverage_check: EssentialCoverageCheck,
) -> ClaimChannelBlock | None:
    insurers = [policy.기본정보.보험사 for policy in policies if policy.기본정보.보험사]
    has_medical_indemnity = any(
        item.kind == "medical_indemnity" and item.status != "not_found"
        for item in essential_coverage_check.items
    )
    if not insurers and not has_medical_indemnity:
        return None

    channels = claim_channel_block(
        insurers,
        has_medical_indemnity=has_medical_indemnity,
    )
    if not channels.insurers and channels.medical_indemnity is None:
        return None
    return ClaimChannelBlock.model_validate(channels.model_dump(mode="python"))


def _single_policy_age(policies: list[PolicyInput]) -> int | None:
    ages = {info.나이 for policy in policies if (info := policy.기본정보.피보험자정보) is not None}
    if len(ages) != 1:
        return None
    return next(iter(ages))


def _premium_benchmark(policies: list[PolicyInput]) -> PremiumBenchmark | None:
    benchmark = premium_benchmark_for_age(_single_policy_age(policies))
    if benchmark is None:
        return None
    return PremiumBenchmark.model_validate(benchmark.model_dump(mode="python"))


def _excluded(policy: PolicyInput, coverage: CoverageInput, reason: str) -> ExcludedCoverageItem:
    return ExcludedCoverageItem(
        policy_id=policy.id,
        insurer=policy.기본정보.보험사,
        product_name=policy.기본정보.상품명,
        coverage_name=coverage.담보명,
        major_category=major_category(coverage.담보명),
        original_amount=coverage.가입금액,
        reason=reason,
    )


def _damage_insurance_type(policy: PolicyInput) -> str:
    category = policy.기본정보.보험분류 or ""
    if category in {"자동차", "자동차보험"}:
        return "자동차보험"
    if category in {"운전자보험", "운전자상해보험"}:
        return "운전자보험"
    if category == "여행자보험":
        return "여행자보험"
    if category in {"화재보험", "주택화재보험"}:
        return "화재보험"
    if category == "배상책임보험":
        return "배상책임보험"
    if category == "보증보험":
        return "보증보험"

    tags = policy.기본정보.상품태그
    for insurance_type in _DAMAGE_INSURANCE_TYPE_ORDER:
        if insurance_type in tags:
            return insurance_type

    if _has_auto_insurance_coverages(policy):
        return "자동차보험"

    product_name = policy.기본정보.상품명 or ""
    normalized_product = normalize_coverage_name(product_name)
    if any(term in normalized_product for term in _normalized_terms(_AUTO_PRODUCT_TERMS)):
        return "자동차보험"
    if any(term in normalized_product for term in _normalized_terms(_FIRE_PRODUCT_TERMS)):
        return "화재보험"
    if _has_fire_insurance_coverages(policy):
        return "화재보험"
    for insurance_type in _DAMAGE_INSURANCE_TYPE_ORDER:
        if normalize_coverage_name(insurance_type) in normalized_product:
            return insurance_type

    return "손해보험"


def _has_auto_insurance_coverages(policy: PolicyInput) -> bool:
    """Infer auto insurance from auto-policy-specific coverage names only."""

    normalized_terms = tuple(normalize_coverage_name(term) for term in _AUTO_COVERAGE_TERMS)
    return any(
        any(term in normalize_coverage_name(coverage.담보명) for term in normalized_terms)
        for coverage in policy.보장목록
    )


def _has_fire_insurance_coverages(policy: PolicyInput) -> bool:
    """Infer fire insurance from fire/property-specific coverage names."""

    normalized_terms = _normalized_terms(_FIRE_COVERAGE_TERMS)
    return any(
        any(term in normalize_coverage_name(coverage.담보명) for term in normalized_terms)
        for coverage in policy.보장목록
    )


def _normalized_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalize_coverage_name(term) for term in terms)


def _damage_policy_group(policy: PolicyInput) -> DamagePolicyCoverageGroup:
    return DamagePolicyCoverageGroup(
        policy_id=policy.id,
        insurer=policy.기본정보.보험사,
        product_name=policy.기본정보.상품명,
        coverages=[
            DamageCoverageItem(
                coverage_name=coverage.담보명,
                original_amount=coverage.가입금액,
                major_category=major_category(coverage.담보명),
            )
            for coverage in policy.보장목록
            if coverage.유형 != "부가"
        ],
    )


def _build_damage_groups(
    damage_rows: dict[str, list[DamagePolicyCoverageGroup]],
) -> list[DamageCoverageGroup]:
    return [
        DamageCoverageGroup(
            insurance_type=insurance_type,
            policies=sorted(policies, key=_damage_policy_sort_key),
        )
        for insurance_type, policies in sorted(
            damage_rows.items(),
            key=lambda item: _damage_insurance_type_rank(item[0]),
        )
    ]


def _damage_insurance_type_rank(insurance_type: str) -> tuple[int, str]:
    try:
        return (_DAMAGE_INSURANCE_TYPE_ORDER.index(insurance_type), insurance_type)
    except ValueError:
        return (len(_DAMAGE_INSURANCE_TYPE_ORDER), insurance_type)


def _damage_policy_sort_key(
    policy: DamagePolicyCoverageGroup,
) -> tuple[str, str, str]:
    return (
        policy.insurer or "",
        policy.product_name or "",
        policy.policy_id or "",
    )


def _build_fixed_totals(
    grouped_sources: dict[str, list[CoverageSourceItem]],
    display_names: dict[str, str],
) -> list[CoverageTotalItem]:
    """Sum only groups with at most one row per known insurer.

    Repeated names from one insurer can represent benefit tiers that cannot be
    aligned safely with another insurer, so those rows remain separate.
    """

    totals: list[CoverageTotalItem] = []
    for name, sources in sorted(grouped_sources.items()):
        ordered_sources = sorted(sources, key=_source_sort_key)
        known_insurers = [source.insurer for source in ordered_sources if source.insurer]
        all_insurers_known = len(known_insurers) == len(ordered_sources)
        can_sum = len(ordered_sources) == 1 or (
            all_insurers_known and len(known_insurers) == len(set(known_insurers))
        )
        groups = [ordered_sources] if can_sum else [[source] for source in ordered_sources]
        for group in groups:
            totals.append(
                CoverageTotalItem(
                    normalized_name=name,
                    display_name=display_names[name],
                    major_category=major_category(display_names[name]),
                    total_amount=sum(source.amount for source in group),
                    coverage_count=len(group),
                    composition=group,
                )
            )
    return totals


def _build_actual_loss_items(
    rows: list[_ActualLossRow],
) -> list[ActualLossCoverageItem]:
    contracts_by_name: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        if row.normalized_name:
            contracts_by_name[row.normalized_name].add(row.contract_index)

    ordered_rows = sorted(
        rows,
        key=lambda row: (
            row.normalized_name,
            row.policy.기본정보.보험사 or "",
            row.policy.기본정보.상품명 or "",
            row.policy.id or "",
            row.coverage.담보명,
        ),
    )
    items: list[ActualLossCoverageItem] = []
    for row in ordered_rows:
        items.append(
            ActualLossCoverageItem(
                policy_id=row.policy.id,
                insurer=row.policy.기본정보.보험사,
                product_name=row.policy.기본정보.상품명,
                coverage_name=row.coverage.담보명,
                original_amount=row.coverage.가입금액,
                normalized_name=row.normalized_name,
                coverage_domain=row.classification.coverage_domain,
                is_medical_indemnity=(row.classification.medical_indemnity_status == "confirmed"),
                duplicate_across_contracts=(
                    bool(row.normalized_name) and len(contracts_by_name[row.normalized_name]) >= 2
                ),
                major_category=major_category(row.coverage.담보명),
            )
        )
    return items


def _source_sort_key(
    source: CoverageSourceItem,
) -> tuple[bool, str, str, str, str, int, str]:
    return (
        source.insurer is None,
        source.insurer or "",
        source.product_name or "",
        source.policy_id or "",
        source.coverage_name,
        source.amount,
        source.original_amount,
    )
