"""Deterministic auto/driver/travel/fire policy facts for counsel.

Thin projection over ``portfolio.special_policies``: it classifies the user's
uploaded non-life policies and checks each for the coverages that matter when a
concrete accident happens (상대방 부상, 내 차량 손해, 변호사 비용, 화재 손해 …).
This file only reshapes that analysis into a compact, LLM-facing bundle and
never runs an LLM itself.
"""

from pydantic import BaseModel

from app.modules.portfolio.schemas import (
    PolicyInput,
    SpecialCoverageCheck,
    SpecialCoverageStatus,
    SpecialPolicyAnalysis,
    SpecialPolicyKind,
)
from app.modules.portfolio.special_policies import build_special_policy_analyses


class SpecialCoverageCheckFact(BaseModel):
    label: str
    status: SpecialCoverageStatus
    status_label: str
    detail: str
    matched_coverage_names: list[str]


class SpecialPolicyFact(BaseModel):
    kind: SpecialPolicyKind
    label: str
    policy_count: int
    product_names: list[str]
    overview: str
    coverage_checks: list[SpecialCoverageCheckFact]


class SpecialPolicyFactBundle(BaseModel):
    analyses: list[SpecialPolicyFact]
    note: str


def build_special_policy_facts(policies: list[PolicyInput]) -> SpecialPolicyFactBundle:
    """Return per-kind coverage checks for the special policies actually held.

    ``build_special_policy_analyses`` already omits kinds with no matching
    policy, so a user without any auto/driver/travel/fire policy yields an empty
    ``analyses`` list -- never a placeholder analysis for coverage they don't
    have.
    """

    analyses = build_special_policy_analyses(policies)

    facts = [_special_policy_fact(analysis) for analysis in analyses]
    return SpecialPolicyFactBundle(analyses=facts, note=_bundle_note(facts))


def _special_policy_fact(analysis: SpecialPolicyAnalysis) -> SpecialPolicyFact:
    return SpecialPolicyFact(
        kind=analysis.kind,
        label=analysis.label,
        policy_count=analysis.policy_count,
        product_names=analysis.product_names,
        overview=analysis.overview,
        coverage_checks=[_coverage_check_fact(check) for check in analysis.coverage_checks],
    )


def _coverage_check_fact(check: SpecialCoverageCheck) -> SpecialCoverageCheckFact:
    return SpecialCoverageCheckFact(
        label=check.label,
        status=check.status,
        status_label=_status_label(check.status),
        detail=check.detail,
        matched_coverage_names=check.matched_coverage_names,
    )


def _status_label(status: SpecialCoverageStatus) -> str:
    if status == "confirmed":
        return "확인됨"
    return "현재 자료에서 미확인"


def _bundle_note(facts: list[SpecialPolicyFact]) -> str:
    if not facts:
        return (
            "업로드된 증권에서 자동차·운전자·여행자·화재보험으로 분류된 계약을 찾지 못했어요. "
            "이런 보험이 있는지 단정하지 말고, 증권을 올렸는지 사용자에게 확인하세요."
        )
    return (
        "각 항목의 status_label과 matched_coverage_names를 그대로 인용하고, 담보명을 "
        "지어내지 마세요. 미확인 항목은 미가입이라고 단정하지 말고, 지급 한도와 면책 "
        "조건은 약관을 더 확인해야 한다고 안내하세요."
    )
