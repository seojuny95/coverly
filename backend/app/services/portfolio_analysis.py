"""Fact-only portfolio analysis without adequacy or policy-term judgments."""

from collections import defaultdict
from typing import Literal

from app.schemas.analysis import (
    AnalysisSource,
    ClassificationAnalysis,
    PortfolioAnalysisResponse,
)
from app.schemas.portfolio import PolicyInput
from app.services.portfolio_summary import PortfolioFacts, build_portfolio_facts

_UNCLASSIFIED = "미분류"


def analyze_portfolio(policies: list[PolicyInput]) -> PortfolioAnalysisResponse:
    """Return descriptive facts; never infer whether coverage is sufficient."""

    facts = build_portfolio_facts(policies)
    classifications = _analyze_classifications(facts)
    summary = facts.coverage_summary
    excluded_count = len(summary.excluded_coverages)
    notices: list[str] = []

    if excluded_count:
        notices.append("일부 담보는 지급유형 또는 금액을 확인할 수 없어 합계에서 제외했습니다.")
    if summary.indemnity_coverages:
        notices.append("실손형 담보는 가입금액 합산 대상이 아니며 보유 건수만 표시합니다.")
    if summary.excluded_auto_policy_count:
        notices.append("자동차 보험은 현재 포트폴리오 합계와 분석에서 제외했습니다.")

    status = _analysis_status(facts)
    return PortfolioAnalysisResponse(
        status=status,
        policy_count=len(facts.policies),
        classification_count=len(classifications),
        confirmed_total_count=len(summary.totals),
        confirmed_total_amount=sum(item.total_amount for item in summary.totals),
        indemnity_coverage_count=len(summary.indemnity_coverages),
        excluded_coverage_count=excluded_count,
        excluded_auto_policy_count=summary.excluded_auto_policy_count,
        classifications=classifications,
        sources=[_source(policy) for policy in facts.policies],
        notices=notices,
    )


def _analyze_classifications(facts: PortfolioFacts) -> list[ClassificationAnalysis]:
    policies_by_classification: dict[str, list[PolicyInput]] = defaultdict(list)
    for policy in facts.policies:
        classification = policy.기본정보.보험분류 or _UNCLASSIFIED
        policies_by_classification[classification].append(policy)

    results: list[ClassificationAnalysis] = []
    for classification, policies in sorted(policies_by_classification.items()):
        class_facts = build_portfolio_facts(policies).coverage_summary
        results.append(
            ClassificationAnalysis(
                classification=classification,
                policy_count=len(policies),
                confirmed_total_count=len(class_facts.totals),
                confirmed_total_amount=sum(item.total_amount for item in class_facts.totals),
                indemnity_coverage_count=len(class_facts.indemnity_coverages),
                excluded_coverage_count=len(class_facts.excluded_coverages),
            )
        )
    return results


def _analysis_status(facts: PortfolioFacts) -> Literal["complete", "partial", "empty"]:
    if not facts.policies:
        return "empty"
    if facts.coverage_summary.excluded_coverages or any(
        policy.분석상태 == "부분" for policy in facts.policies
    ):
        return "partial"
    return "complete"


def _source(policy: PolicyInput) -> AnalysisSource:
    return AnalysisSource(
        policy_id=policy.id,
        insurer=policy.기본정보.보험사,
        product_name=policy.기본정보.상품명,
    )
