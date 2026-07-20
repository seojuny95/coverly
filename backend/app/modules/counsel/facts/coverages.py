"""Deterministic coverage facts for counsel."""

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from app.modules.coverage.contracts import CoverageType
from app.modules.portfolio.schemas import PolicyInput

CoverageExplanationBasis = Literal["policy_wording", "generated_guidance", "none"]


class CoverageNameInfo(BaseModel):
    담보명: str
    지급유형: str | None
    유형: CoverageType | None = None
    보장분류: str | None = None
    보장내용: str | None = None
    해설: str | None = None
    설명근거: CoverageExplanationBasis = "none"


class CoverageMatch(BaseModel):
    policy_id: str | None
    보험사: str | None
    상품명: str | None
    담보명: str
    가입금액: str
    가입금액숫자: int | None
    지급유형: str | None
    유형: CoverageType | None = None
    보장분류: str | None = None
    보장내용: str | None = None
    해설: str | None = None
    설명근거: CoverageExplanationBasis = "none"


class UnmatchedCoverageName(BaseModel):
    requested_name: str
    candidates: list[str]


class FindCoveragesResult(BaseModel):
    matches: list[CoverageMatch]
    unmatched: list[UnmatchedCoverageName]


class ExcludedCoverage(BaseModel):
    policy_id: str | None
    보험사: str | None
    상품명: str | None
    담보명: str
    reason: str


class CoverageTotalResult(BaseModel):
    total: int
    included: list[CoverageMatch]
    excluded: list[ExcludedCoverage]
    unmatched: list[UnmatchedCoverageName]


class OverlapEntry(BaseModel):
    policy_id: str | None
    보험사: str | None
    상품명: str | None
    가입금액: str
    가입금액숫자: int | None
    지급유형: str | None
    유형: CoverageType | None = None
    보장분류: str | None = None


class OverlappingCoverage(BaseModel):
    담보명: str
    policies: list[OverlapEntry]


def list_coverage_name_facts(policies: list[PolicyInput]) -> list[CoverageNameInfo]:
    """Return every distinct coverage name with its payment type."""

    info_by_name: dict[str, CoverageNameInfo] = {}
    for policy in policies:
        for coverage in policy.보장목록:
            info_by_name.setdefault(
                coverage.담보명,
                CoverageNameInfo(
                    담보명=coverage.담보명,
                    지급유형=coverage.지급유형,
                    유형=coverage.유형,
                    보장분류=coverage.보장분류,
                    보장내용=coverage.보장내용,
                    해설=coverage.해설,
                    설명근거=_explanation_basis(coverage.보장내용, coverage.해설),
                ),
            )

    return [info_by_name[name] for name in sorted(info_by_name)]


def find_coverage_facts(
    policies: list[PolicyInput],
    coverage_names: list[str],
) -> FindCoveragesResult:
    """Exact-match coverage names across policies; report candidates, never guess."""

    matches, unmatched = match_coverage_names(policies, coverage_names)
    return FindCoveragesResult(matches=matches, unmatched=unmatched)


def calculate_coverage_total_fact(
    policies: list[PolicyInput],
    coverage_names: list[str],
) -> CoverageTotalResult:
    """Calculate the total fixed amount for exact coverage names."""

    matches, unmatched = match_coverage_names(policies, coverage_names)

    included = [item for item in matches if item.가입금액숫자 is not None]
    excluded = [
        ExcludedCoverage(
            policy_id=item.policy_id,
            보험사=item.보험사,
            상품명=item.상품명,
            담보명=item.담보명,
            reason="실손형이거나 고정 가입금액이 확인되지 않아 합계에서 제외했습니다.",
        )
        for item in matches
        if item.가입금액숫자 is None
    ]
    total = sum(item.가입금액숫자 for item in included if item.가입금액숫자 is not None)
    return CoverageTotalResult(
        total=total,
        included=included,
        excluded=excluded,
        unmatched=unmatched,
    )


def find_overlapping_coverage_facts(
    policies: list[PolicyInput],
) -> list[OverlappingCoverage]:
    """Return coverage names that appear in two or more policies."""

    groups: dict[str, list[OverlapEntry]] = defaultdict(list)
    for policy in policies:
        for coverage in policy.보장목록:
            groups[coverage.담보명].append(
                OverlapEntry(
                    policy_id=policy.id,
                    보험사=policy.기본정보.보험사,
                    상품명=policy.기본정보.상품명,
                    가입금액=coverage.가입금액,
                    가입금액숫자=coverage.가입금액숫자,
                    지급유형=coverage.지급유형,
                    유형=coverage.유형,
                    보장분류=coverage.보장분류,
                )
            )

    return [
        OverlappingCoverage(담보명=name, policies=entries)
        for name, entries in sorted(groups.items())
        if len(entries) > 1
    ]


def match_coverage_names(
    policies: list[PolicyInput],
    coverage_names: list[str],
) -> tuple[list[CoverageMatch], list[UnmatchedCoverageName]]:
    """Exact-match coverage_names across policies; report candidates, never guess."""

    all_names = _all_coverage_names(policies)
    requested = {name.strip() for name in coverage_names}
    matches: list[CoverageMatch] = []
    found_names: set[str] = set()

    for policy in policies:
        for coverage in policy.보장목록:
            if coverage.담보명 not in requested:
                continue
            matches.append(
                CoverageMatch(
                    policy_id=policy.id,
                    보험사=policy.기본정보.보험사,
                    상품명=policy.기본정보.상품명,
                    담보명=coverage.담보명,
                    가입금액=coverage.가입금액,
                    가입금액숫자=coverage.가입금액숫자,
                    지급유형=coverage.지급유형,
                    유형=coverage.유형,
                    보장분류=coverage.보장분류,
                    보장내용=coverage.보장내용,
                    해설=coverage.해설,
                    설명근거=_explanation_basis(coverage.보장내용, coverage.해설),
                )
            )
            found_names.add(coverage.담보명)

    unmatched = [
        UnmatchedCoverageName(
            requested_name=name,
            candidates=sorted(c for c in all_names if c.startswith(name)),
        )
        for name in sorted(requested - found_names)
    ]
    return matches, unmatched


def _all_coverage_names(policies: list[PolicyInput]) -> set[str]:
    return {coverage.담보명 for policy in policies for coverage in policy.보장목록}


def _explanation_basis(
    policy_wording: str | None,
    generated_guidance: str | None,
) -> CoverageExplanationBasis:
    if policy_wording:
        return "policy_wording"
    if generated_guidance:
        return "generated_guidance"
    return "none"
