"""Death benefit classification for portfolio essential coverage checks."""

from dataclasses import dataclass
from typing import Literal

from app.modules.portfolio.amounts import normalized_terms, parse_amount
from app.modules.portfolio.death_benefit_guides import DeathBenefitGuide
from app.modules.portfolio.essential_guides import EssentialCoverageGuide
from app.modules.portfolio.schemas import (
    CoverageGroup,
    CoverageGroupTone,
    CoverageInput,
    EssentialCoverageItem,
    EssentialCoverageStatus,
    PolicyInput,
)

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

DeathCoverageKind = Literal["primary", "accident", "limited"]


@dataclass(frozen=True)
class _DeathCoverageMatch:
    coverage: CoverageInput
    kind: DeathCoverageKind


def build_death_coverage_item(
    policies: list[PolicyInput],
    *,
    guide: EssentialCoverageGuide,
    death_guide: DeathBenefitGuide,
) -> EssentialCoverageItem:
    matches = [
        _DeathCoverageMatch(coverage=coverage, kind=kind)
        for policy in policies
        for coverage in policy.보장목록
        if (kind := _death_coverage_kind(coverage.담보명)) is not None
    ]
    primary_coverages = [match.coverage for match in matches if match.kind == "primary"]
    primary_amounts = [
        amount for coverage in primary_coverages if (amount := parse_amount(coverage)) is not None
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
    normalized_name = normalized_terms((name,))[0]
    if "사망" not in normalized_name:
        return None
    if any(term in normalized_name for term in normalized_terms(_LIMITED_DEATH_TERMS)):
        return "limited"
    if any(term in normalized_name for term in normalized_terms(_ACCIDENT_DEATH_TERMS)):
        return "accident"
    if any(term in normalized_name for term in normalized_terms(_PRIMARY_DEATH_TERMS)):
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
        coverages = [match.coverage for match in matches if match.kind == kind]
        names = sorted({coverage.담보명 for coverage in coverages})
        if not names:
            continue
        amounts = [
            amount for coverage in coverages if (amount := parse_amount(coverage)) is not None
        ]
        groups.append(
            CoverageGroup(
                label=label,
                tone=tone,
                detail=detail,
                coverage_names=names,
                total_amount=sum(amounts) if amounts else None,
            )
        )
    return groups
