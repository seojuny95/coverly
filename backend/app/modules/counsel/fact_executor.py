"""Execute planned counsel fact tasks against deterministic fact modules."""

from pydantic import BaseModel

from app.modules.counsel.facts.claims import ClaimChannelsResult, get_claim_channel_facts
from app.modules.counsel.facts.coverages import (
    CoverageNameInfo,
    CoverageTotalResult,
    FindCoveragesResult,
    OverlappingCoverage,
    calculate_coverage_total_fact,
    find_coverage_facts,
    find_overlapping_coverage_facts,
    list_coverage_name_facts,
)
from app.modules.counsel.facts.policies import PolicyListResult, list_policy_facts
from app.modules.counsel.facts.portfolio import PortfolioFactBundle, build_portfolio_fact_bundle
from app.modules.counsel.planner import CounselPlan, CounselTask
from app.modules.portfolio.schemas import PolicyInput


class FactTaskResult(BaseModel):
    task: CounselTask
    policy_list: PolicyListResult | None = None
    coverage_names: list[CoverageNameInfo] | None = None
    coverage_lookup: FindCoveragesResult | None = None
    coverage_total: CoverageTotalResult | None = None
    overlaps: list[OverlappingCoverage] | None = None
    claim_channels: ClaimChannelsResult | None = None
    portfolio_bundle: PortfolioFactBundle | None = None


class FactExecution(BaseModel):
    results: list[FactTaskResult]

    @property
    def has_results(self) -> bool:
        return bool(self.results)


def execute_fact_tasks(plan: CounselPlan, policies: list[PolicyInput]) -> FactExecution:
    """Run deterministic fact tasks selected by the planner."""

    results: list[FactTaskResult] = []
    for task in plan.tasks:
        result = _execute_task(task, policies)
        if result is not None:
            results.append(result)
    return FactExecution(results=results)


def _execute_task(task: CounselTask, policies: list[PolicyInput]) -> FactTaskResult | None:
    if task.kind in {"policy_count", "policy_list"}:
        return FactTaskResult(task=task, policy_list=list_policy_facts(policies))
    if task.kind == "coverage_list":
        return FactTaskResult(
            task=task,
            coverage_names=list_coverage_name_facts(policies),
        )
    if task.kind == "coverage_lookup":
        return FactTaskResult(
            task=task,
            coverage_lookup=find_coverage_facts(policies, task.coverage_names),
        )
    if task.kind == "coverage_total":
        return FactTaskResult(
            task=task,
            coverage_total=calculate_coverage_total_fact(policies, task.coverage_names),
        )
    if task.kind == "overlap_check":
        return FactTaskResult(task=task, overlaps=find_overlapping_coverage_facts(policies))
    if task.kind == "claim_channel":
        return FactTaskResult(
            task=task,
            claim_channels=get_claim_channel_facts(policies, task.coverage_names),
        )
    if task.kind == "portfolio_review":
        return FactTaskResult(task=task, portfolio_bundle=build_portfolio_fact_bundle(policies))
    return None
