"""Agent SDK tools for coverage discovery, lookup, totals, and overlaps."""

from collections import defaultdict

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel

from app.modules.counsel.context import CounselContext
from app.modules.portfolio.schemas import PolicyInput


def _all_coverage_names(policies: list[PolicyInput]) -> set[str]:
    return {coverage.담보명 for policy in policies for coverage in policy.보장목록}


@function_tool
def list_coverage_names(wrapper: RunContextWrapper[CounselContext]) -> list[str]:
    """사용자 증권 전체의 정확한 담보명을 모두 나열합니다.

    정확한 담보명이 확실하지 않으면(예: "(유사암제외)", "(감액없음)" 같은 접미사가
    붙는 경우가 많습니다) find_coverages를 부르기 전에 먼저 이 도구를 호출하세요.
    """

    return sorted(_all_coverage_names(wrapper.context.policies))


class CoverageMatch(BaseModel):
    보험사: str | None
    상품명: str | None
    담보명: str
    가입금액: str
    가입금액숫자: int | None
    지급유형: str | None


class UnmatchedCoverageName(BaseModel):
    requested_name: str
    candidates: list[str]


def _match_coverage_names(
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
                    보험사=policy.기본정보.보험사,
                    상품명=policy.기본정보.상품명,
                    담보명=coverage.담보명,
                    가입금액=coverage.가입금액,
                    가입금액숫자=coverage.가입금액숫자,
                    지급유형=coverage.지급유형,
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


class FindCoveragesResult(BaseModel):
    matches: list[CoverageMatch]
    unmatched: list[UnmatchedCoverageName]


@function_tool
def find_coverages(
    wrapper: RunContextWrapper[CounselContext],
    coverage_names: list[str],
) -> FindCoveragesResult:
    """사용자 증권에서 특정 담보를 정확한 이름으로 조회합니다.

    요청한 이름이 정확히 일치하지 않지만 결과에 candidates가 있으면, 임의로
    하나를 골라 답하지 마세요. 후보를 제시하고 사용자에게 어떤 담보를
    말하는지 되물으세요.

    Args:
        coverage_names: 조회할 정확한 담보명 목록입니다. 정확한 철자가
            확실하지 않으면(예: "(유사암제외)" 같은 접미사) 먼저
            list_coverage_names를 호출하세요. 정확히 일치하지 않는 이름은
            임의로 추측하거나 합쳐지지 않고, 같은 접두어를 가진 후보
            이름으로 보고됩니다.
    """

    matches, unmatched = _match_coverage_names(wrapper.context.policies, coverage_names)
    return FindCoveragesResult(matches=matches, unmatched=unmatched)


class ExcludedCoverage(BaseModel):
    보험사: str | None
    상품명: str | None
    담보명: str
    reason: str


class CoverageTotalResult(BaseModel):
    total: int
    included: list[CoverageMatch]
    excluded: list[ExcludedCoverage]
    unmatched: list[UnmatchedCoverageName]


@function_tool
def calculate_coverage_total(
    wrapper: RunContextWrapper[CounselContext],
    coverage_names: list[str],
) -> CoverageTotalResult:
    """지정한 담보들의 가입금액 합계를 정확히 계산합니다. 직접 암산하지 마세요.

    합계는 코드가 계산하며, 실손형처럼 고정 가입금액이 없는 담보는 합계에서
    제외되고 excluded에 이유와 함께 보고됩니다(0으로 취급하지 않습니다).
    사용자가 명시적으로 요청한 담보만 coverage_names에 넣으세요 — 사용자가
    언급하지 않은 관련 담보를 임의로 추가해 합치지 마세요.

    Args:
        coverage_names: 합산할 정확한 담보명 목록입니다. 정확한 철자가
            확실하지 않으면 먼저 list_coverage_names를 호출하세요.
    """

    matches, unmatched = _match_coverage_names(wrapper.context.policies, coverage_names)

    included = [item for item in matches if item.가입금액숫자 is not None]
    excluded = [
        ExcludedCoverage(
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
        total=total, included=included, excluded=excluded, unmatched=unmatched
    )


class OverlapEntry(BaseModel):
    보험사: str | None
    상품명: str | None
    가입금액: str
    가입금액숫자: int | None
    지급유형: str | None


class OverlappingCoverage(BaseModel):
    담보명: str
    policies: list[OverlapEntry]


@function_tool
def find_overlapping_coverages(
    wrapper: RunContextWrapper[CounselContext],
) -> list[OverlappingCoverage]:
    """같은 담보명이 두 개 이상의 증권에 중복 가입된 경우를 모두 나열합니다.

    중복 여부만 사실대로 알려주고, 해지하거나 줄이라고 권유하지 마세요.
    """

    groups: dict[str, list[OverlapEntry]] = defaultdict(list)
    for policy in wrapper.context.policies:
        for coverage in policy.보장목록:
            groups[coverage.담보명].append(
                OverlapEntry(
                    보험사=policy.기본정보.보험사,
                    상품명=policy.기본정보.상품명,
                    가입금액=coverage.가입금액,
                    가입금액숫자=coverage.가입금액숫자,
                    지급유형=coverage.지급유형,
                )
            )

    return [
        OverlappingCoverage(담보명=name, policies=entries)
        for name, entries in sorted(groups.items())
        if len(entries) > 1
    ]
