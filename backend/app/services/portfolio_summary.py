"""Deterministic, non-RAG portfolio coverage aggregation."""

import re
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from app.schemas.portfolio import (
    CoverageInput,
    CoverageSourceItem,
    CoverageTotalItem,
    ExcludedCoverageItem,
    IndemnityItem,
    PolicyInput,
    PortfolioCoverageSummary,
)
from app.services.coverage_name_matching import (
    canonicalize_coverage_name,
    choose_display_name,
)

_AUTO_CATEGORY_TERMS = ("자동차",)
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
    "진단비",
    "수술비",
    "치료비",
    "입원",
    "통원",
    "후유장해",
    "사망",
    "간병",
    "기타",
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
    if "후유장해" in normalized:
        return "후유장해"
    if "수술" in normalized:
        return "수술비"
    if "간병" in normalized or "요양" in normalized:
        return "간병"
    if "진단" in normalized or "악성신생물" in normalized:
        return "진단비"
    if "사망" in normalized:
        return "사망"
    if "치료비" in normalized or "의료비" in normalized:
        return "치료비"
    if "입원" in normalized:
        return "입원"
    if "통원" in normalized:
        return "통원"
    return "기타"


def is_auto_policy(policy: PolicyInput) -> bool:
    """Return whether a policy belongs to the separately handled auto branch."""

    category = policy.기본정보.보험분류 or ""
    return any(term in category for term in _AUTO_CATEGORY_TERMS)


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
    auto_count = 0

    for policy in policies:
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
    return PortfolioCoverageSummary(
        totals=totals,
        indemnity_coverages=indemnity,
        excluded_coverages=excluded,
        excluded_auto_policy_count=auto_count,
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
        policies=tuple(policy for policy in policies if not is_auto_policy(policy)),
        coverage_summary=summarize_portfolio_coverages(policies),
    )


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
