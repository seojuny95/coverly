"""Build and derive the grounded context used by QA answer strategies."""

from dataclasses import dataclass

from app.modules.coverage.taxonomy import LifeStageCheck, check_life_stage
from app.modules.evidence.catalog import EvidenceCatalog, build_evidence_catalog
from app.modules.portfolio.damage_classification import is_auto_policy
from app.modules.portfolio.demographics import resolve_portfolio_demographics
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.summary import PortfolioFacts, build_portfolio_facts
from app.modules.qa.contracts import InsuredDemographics
from app.modules.qa.schemas import ConversationMessage, recent_history


@dataclass(frozen=True)
class QaContext:
    """Portfolio facts and evidence needed to answer one normalized question."""

    question: str
    policies: list[PolicyInput]
    history: list[ConversationMessage]
    insured: InsuredDemographics
    facts: PortfolioFacts
    auto_policies: tuple[PolicyInput, ...]
    life_stage_check: LifeStageCheck
    catalog: EvidenceCatalog
    policy_rag_session_ids: tuple[str, ...] = ()


def build_qa_context(
    question: str,
    policies: list[PolicyInput],
    demographics: InsuredDemographics | None,
    history: list[ConversationMessage] | None,
    *,
    policy_rag_session_ids: tuple[str, ...] = (),
) -> QaContext:
    insured = resolve_portfolio_demographics(policies, demographics)
    facts = build_portfolio_facts(policies)
    auto_policies = tuple(policy for policy in policies if is_auto_policy(policy))
    life_stage_check = _life_stage_check(insured, facts)
    catalog = build_evidence_catalog(facts, insured, life_stage_check.missing, auto_policies)

    return QaContext(
        question=question.strip(),
        policies=policies,
        history=recent_history(history),
        insured=insured,
        facts=facts,
        auto_policies=auto_policies,
        life_stage_check=life_stage_check,
        catalog=catalog,
        policy_rag_session_ids=policy_rag_session_ids,
    )


def _life_stage_check(
    demographics: InsuredDemographics,
    facts: PortfolioFacts,
) -> LifeStageCheck:
    if demographics.age is None:
        return LifeStageCheck(life_stage="미상", held=(), missing=())
    coverage_names = [coverage.담보명 for policy in facts.policies for coverage in policy.보장목록]
    if any(item.is_medical_indemnity for item in facts.coverage_summary.actual_loss_coverages):
        coverage_names.append("실손의료비")
    return check_life_stage(demographics.age, coverage_names)
