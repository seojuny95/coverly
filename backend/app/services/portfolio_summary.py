"""Deterministic, non-RAG portfolio coverage aggregation."""

import re
from collections import defaultdict
from dataclasses import dataclass

from app.schemas.portfolio import (
    CoverageInput,
    CoverageSourceItem,
    CoverageTotalItem,
    ExcludedCoverageItem,
    IndemnityItem,
    PolicyInput,
    PortfolioCoverageSummary,
)

_AUTO_CATEGORY_TERMS = ("자동차",)
_INDEMNITY_TERMS = ("실손", "실비", "실손의료", "실손보상")
_FIXED_PAYMENT_TERMS = ("정액", "고정액")
_INDEMNITY_PAYMENT_TERMS = ("실손", "실비", "비례", "실액")
_SAFE_FIXED_NAME_TERMS = ("진단비", "수술비", "입원일당", "입원비", "사망", "후유장해")
_UNITS = {
    "원": 1,
    "천원": 1_000,
    "만원": 10_000,
    "백만원": 1_000_000,
    "천만원": 10_000_000,
    "억원": 100_000_000,
}


@dataclass(frozen=True)
class PortfolioFacts:
    """Stable facts reusable by analysis and Q&A without introducing RAG."""

    policies: tuple[PolicyInput, ...]
    coverage_summary: PortfolioCoverageSummary


def normalize_coverage_name(name: str) -> str:
    """Normalize formatting only, avoiding semantic aliases that can over-group."""

    return re.sub(r"[^0-9A-Za-z가-힣]", "", name).casefold()


def _is_auto_policy(policy: PolicyInput) -> bool:
    category = policy.기본정보.보험분류 or ""
    return any(term in category for term in _AUTO_CATEGORY_TERMS)


def _is_indemnity(coverage: CoverageInput) -> bool:
    payment_type = coverage.지급유형 or ""
    if any(term in payment_type for term in _INDEMNITY_PAYMENT_TERMS):
        return True
    searchable = " ".join((coverage.담보명, coverage.보장분류 or ""))
    return any(term in searchable for term in _INDEMNITY_TERMS)


def _is_safe_fixed(coverage: CoverageInput) -> bool:
    payment_type = coverage.지급유형 or ""
    if any(term in payment_type for term in _FIXED_PAYMENT_TERMS):
        return True
    if payment_type:
        return False
    return any(term in coverage.담보명 for term in _SAFE_FIXED_NAME_TERMS)


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
    display_names: dict[str, str] = {}
    indemnity_rows: list[tuple[PolicyInput, CoverageInput, str]] = []
    excluded: list[ExcludedCoverageItem] = []
    auto_count = 0

    for policy in policies:
        if _is_auto_policy(policy):
            auto_count += 1
            continue
        for coverage in policy.보장목록:
            normalized_name = normalize_coverage_name(coverage.담보명)
            if _is_indemnity(coverage):
                indemnity_rows.append((policy, coverage, normalized_name))
                continue
            if not _is_safe_fixed(coverage):
                excluded.append(_excluded(policy, coverage, "지급유형을 안전하게 확인할 수 없음"))
                continue
            amount = _parse_amount(coverage)
            if amount is None:
                excluded.append(_excluded(policy, coverage, "가입금액을 숫자로 확인할 수 없음"))
                continue
            if not normalized_name:
                excluded.append(_excluded(policy, coverage, "담보명을 정규화할 수 없음"))
                continue
            display_names.setdefault(normalized_name, coverage.담보명)
            grouped_sources[normalized_name].append(
                CoverageSourceItem(
                    policy_id=policy.id,
                    insurer=policy.기본정보.보험사,
                    product_name=policy.기본정보.상품명,
                    coverage_name=coverage.담보명,
                    amount=amount,
                    original_amount=coverage.가입금액,
                )
            )

    totals = _build_fixed_totals(grouped_sources, display_names)
    indemnity = _build_indemnity_items(indemnity_rows)
    return PortfolioCoverageSummary(
        totals=totals,
        indemnity_coverages=indemnity,
        excluded_coverages=excluded,
        excluded_auto_policy_count=auto_count,
    )


def build_portfolio_facts(policies: list[PolicyInput]) -> PortfolioFacts:
    """Build the deterministic common input for summary, analysis, and Q&A."""

    return PortfolioFacts(
        policies=tuple(policies),
        coverage_summary=summarize_portfolio_coverages(policies),
    )


def _excluded(policy: PolicyInput, coverage: CoverageInput, reason: str) -> ExcludedCoverageItem:
    return ExcludedCoverageItem(
        policy_id=policy.id,
        coverage_name=coverage.담보명,
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
        known_insurers = [source.insurer for source in sources if source.insurer]
        all_insurers_known = len(known_insurers) == len(sources)
        can_sum = len(sources) == 1 or (
            all_insurers_known and len(known_insurers) == len(set(known_insurers))
        )
        groups = [sources] if can_sum else [[source] for source in sources]
        for group in groups:
            totals.append(
                CoverageTotalItem(
                    normalized_name=name,
                    display_name=display_names[name],
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

    items: list[IndemnityItem] = []
    for policy, coverage, normalized_name in rows:
        items.append(
            IndemnityItem(
                policy_id=policy.id,
                insurer=policy.기본정보.보험사,
                product_name=policy.기본정보.상품명,
                coverage_name=coverage.담보명,
                normalized_name=normalized_name,
                cross_insurer_duplicate=len(insurers_by_name[normalized_name]) >= 2,
            )
        )
    return items
