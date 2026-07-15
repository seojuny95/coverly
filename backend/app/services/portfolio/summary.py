"""Deterministic, non-RAG portfolio coverage aggregation."""

import re
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from app.schemas.portfolio import (
    ClaimChannelBlock,
    CoverageInput,
    CoverageSourceItem,
    CoverageTotalItem,
    DamageCoverageGroup,
    DamageCoverageItem,
    DamagePolicyCoverageGroup,
    EssentialCoverageCheck,
    ExcludedCoverageItem,
    IndemnityItem,
    PolicyInput,
    PortfolioCoverageSummary,
    PremiumBenchmark,
    PremiumOverview,
)
from app.services.coverage_knowledge.matching import (
    canonicalize_coverage_name,
    choose_display_name,
)
from app.services.portfolio.essential_coverage import (
    build_essential_coverage_check,
    build_special_policy_analyses,
)
from app.services.portfolio.premium import summarize_premiums
from app.services.qa.claim_channels import claim_channel_block
from app.services.reference.premium_benchmark import premium_benchmark_for_age

_DAMAGE_CLASSIFICATION = "손해보험"
_LEGACY_DAMAGE_CLASSIFICATIONS = frozenset(
    {
        "자동차",
        "자동차보험",
        "운전자보험",
        "운전자상해보험",
        "여행자보험",
        "화재보험",
        "주택화재보험",
        "배상책임보험",
        "보증보험",
        "배상·화재·기타",
    }
)
_AUTO_TAG_TERMS = ("자동차", "자동차보험")
_INDEMNITY_NAME_TERMS = ("실손", "실비")
_INDEMNITY_CATEGORIES = frozenset({"실손", "실손형", "실비", "실비형"})
_NEGATED_INDEMNITY_PATTERNS = (
    "비실손",
    "비실비",
    "실손제외",
    "실비제외",
    "실손미해당",
    "실비미해당",
    "실손아님",
    "실비아님",
    "실손비대상",
    "실비비대상",
    "실손미포함",
    "실비미포함",
)
_FIXED_PAYMENT_TYPES = frozenset({"정액", "정액형", "고정액", "고정액형"})
_INDEMNITY_PAYMENT_TYPES = frozenset(
    {
        "실손",
        "실손형",
        "실비",
        "실비형",
        "비례",
        "비례형",
        "비례보상",
        "실액",
        "실액형",
        "실액보상",
    }
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


class _PayoutKind(Enum):
    FIXED = "fixed"
    INDEMNITY = "indemnity"
    UNKNOWN = "unknown"


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

    category = policy.기본정보.보험분류 or ""
    return category == _DAMAGE_CLASSIFICATION or category in _LEGACY_DAMAGE_CLASSIFICATIONS


def is_auto_policy(policy: PolicyInput) -> bool:
    """Return whether a policy is an auto policy inside the damage branch."""

    return any(term in _damage_insurance_type(policy) for term in _AUTO_TAG_TERMS)


def _classify_payout_kind(coverage: CoverageInput) -> _PayoutKind:
    """Classify explicit payment evidence before conservative name inference."""

    payment_type = (coverage.지급유형 or "").strip()
    if payment_type in _INDEMNITY_PAYMENT_TYPES:
        return _PayoutKind.INDEMNITY
    if payment_type in _FIXED_PAYMENT_TYPES:
        return _PayoutKind.FIXED
    if payment_type:
        return _PayoutKind.UNKNOWN

    coverage_category = (coverage.보장분류 or "").strip()
    normalized_name = normalize_coverage_name(coverage.담보명)
    normalized_category = normalize_coverage_name(coverage_category)
    has_negated_indemnity = any(
        pattern in normalized_name or pattern in normalized_category
        for pattern in _NEGATED_INDEMNITY_PATTERNS
    )
    if has_negated_indemnity:
        return _PayoutKind.UNKNOWN
    if coverage_category in _INDEMNITY_CATEGORIES:
        return _PayoutKind.INDEMNITY
    if any(term in normalized_name for term in _INDEMNITY_NAME_TERMS):
        return _PayoutKind.INDEMNITY
    if any(term in coverage.담보명 for term in _SAFE_FIXED_NAME_TERMS):
        return _PayoutKind.FIXED

    return _PayoutKind.UNKNOWN


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


def summarize_portfolio_coverages(policies: list[PolicyInput]) -> PortfolioCoverageSummary:
    """Aggregate only amounts whose fixed-benefit meaning and value are safe."""

    grouped_sources: dict[str, list[CoverageSourceItem]] = defaultdict(list)
    source_names_by_group: dict[str, list[str]] = defaultdict(list)
    indemnity_rows: list[tuple[PolicyInput, CoverageInput, str]] = []
    excluded: list[ExcludedCoverageItem] = []
    damage_rows: dict[str, list[DamagePolicyCoverageGroup]] = defaultdict(list)
    auto_count = 0

    for policy in policies:
        if is_damage_policy(policy):
            damage_rows[_damage_insurance_type(policy)].append(_damage_policy_group(policy))
            if is_auto_policy(policy):
                auto_count += 1
            continue
        for coverage in policy.보장목록:
            group_key = canonicalize_coverage_name(coverage.담보명).normalized_key
            payout_kind = _classify_payout_kind(coverage)
            if payout_kind is _PayoutKind.INDEMNITY:
                indemnity_rows.append((policy, coverage, group_key))
                continue
            if payout_kind is _PayoutKind.UNKNOWN:
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
    indemnity = _build_indemnity_items(indemnity_rows)
    excluded.sort(
        key=lambda item: (
            item.policy_id or "",
            item.coverage_name,
            item.original_amount,
            item.reason,
        )
    )
    essential_coverage_check = build_essential_coverage_check(policies)
    summary = PortfolioCoverageSummary(
        totals=totals,
        indemnity_coverages=indemnity,
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


def count_duplicate_indemnity_coverages(summary: PortfolioCoverageSummary) -> int:
    """Count distinct indemnity coverage names duplicated across ≥2 insurers.

    Duplicated indemnity coverage cannot pay out more (비례보상), so this is the
    'can be tidied up' signal — counted by distinct coverage, not by row.
    """

    duplicated = {
        item.normalized_name for item in summary.indemnity_coverages if item.cross_insurer_duplicate
    }
    return len(duplicated)


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
    has_indemnity = any(
        item.kind == "indemnity" and item.status != "not_found"
        for item in essential_coverage_check.items
    )
    if not insurers and not has_indemnity:
        return None

    channels = claim_channel_block(insurers, has_indemnity=has_indemnity)
    if not channels.insurers and channels.indemnity is None:
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

    product_name = policy.기본정보.상품명 or ""
    normalized_product = normalize_coverage_name(product_name)
    for insurance_type in _DAMAGE_INSURANCE_TYPE_ORDER:
        if normalize_coverage_name(insurance_type) in normalized_product:
            return insurance_type

    return "손해보험"


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


def _build_indemnity_items(
    rows: list[tuple[PolicyInput, CoverageInput, str]],
) -> list[IndemnityItem]:
    insurers_by_name: dict[str, set[str]] = defaultdict(set)
    for policy, _, normalized_name in rows:
        insurer = policy.기본정보.보험사
        if insurer:
            insurers_by_name[normalized_name].add(insurer)

    ordered_rows = sorted(
        rows,
        key=lambda row: (
            row[2],
            row[0].기본정보.보험사 or "",
            row[0].기본정보.상품명 or "",
            row[0].id or "",
            row[1].담보명,
        ),
    )
    items: list[IndemnityItem] = []
    for policy, coverage, normalized_name in ordered_rows:
        items.append(
            IndemnityItem(
                policy_id=policy.id,
                insurer=policy.기본정보.보험사,
                product_name=policy.기본정보.상품명,
                coverage_name=coverage.담보명,
                original_amount=coverage.가입금액,
                normalized_name=normalized_name,
                cross_insurer_duplicate=len(insurers_by_name[normalized_name]) >= 2,
                major_category=major_category(coverage.담보명),
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
