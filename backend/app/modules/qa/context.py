"""Build and derive the grounded context used by QA answer strategies."""

from dataclasses import dataclass

from app.modules.coverage.indemnity import classify_indemnity
from app.modules.coverage.matching import canonicalize_coverage_name
from app.modules.coverage.taxonomy import LifeStageCheck, check_life_stage
from app.modules.evidence.catalog import EvidenceCatalog, build_evidence_catalog
from app.modules.portfolio.demographics import resolve_portfolio_demographics
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.summary import PortfolioFacts, build_portfolio_facts, is_auto_policy
from app.modules.qa.contracts import InsuredDemographics
from app.modules.qa.schemas import ConversationMessage


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


@dataclass(frozen=True)
class ClaimTarget:
    normalized_name: str
    insurer: str
    is_medical_indemnity: bool
    policy_terms: tuple[str, ...]


def build_qa_context(
    question: str,
    policies: list[PolicyInput],
    demographics: InsuredDemographics | None,
    history: list[ConversationMessage] | None,
) -> QaContext:
    insured = resolve_portfolio_demographics(policies, demographics)
    facts = build_portfolio_facts(policies)
    auto_policies = tuple(policy for policy in policies if is_auto_policy(policy))
    life_stage_check = _life_stage_check(insured, facts)
    catalog = build_evidence_catalog(facts, insured, life_stage_check.missing, auto_policies)

    return QaContext(
        question=question.strip(),
        policies=policies,
        history=history or [],
        insured=insured,
        facts=facts,
        auto_policies=auto_policies,
        life_stage_check=life_stage_check,
        catalog=catalog,
    )


def context_with_question(context: QaContext, question: str) -> QaContext:
    return QaContext(
        question=question.strip(),
        policies=context.policies,
        history=context.history,
        insured=context.insured,
        facts=context.facts,
        auto_policies=context.auto_policies,
        life_stage_check=context.life_stage_check,
        catalog=context.catalog,
    )


def claim_targets(context: QaContext) -> list[ClaimTarget]:
    """Map held coverages to their policy insurers for claim-channel routing.

    Base-name normalization drops qualifiers such as ``(유사암제외)`` so a
    conversational mention can still resolve to the insurer on the original
    policy rather than to an insurer-less multi-policy total.
    """

    targets: list[ClaimTarget] = []
    for policy in context.policies:
        insurer = policy.기본정보.보험사
        if not insurer:
            continue
        policy_terms = tuple(
            dict.fromkeys(
                normalized
                for value in (
                    insurer,
                    policy.기본정보.상품명,
                    *policy.기본정보.상품태그,
                )
                if value and (normalized := base_normalized_coverage_name(value))
            )
        )
        for coverage in policy.보장목록:
            normalized = base_normalized_coverage_name(coverage.담보명)
            if normalized:
                classification = classify_indemnity(coverage, policy=policy)
                targets.append(
                    ClaimTarget(
                        normalized_name=normalized,
                        insurer=insurer,
                        is_medical_indemnity=(
                            classification.medical_indemnity_status == "confirmed"
                        ),
                        policy_terms=policy_terms,
                    )
                )
    return targets


def base_normalized_coverage_name(coverage_name: str) -> str:
    """Normalize a coverage base name without parenthesized qualifiers."""

    base_name = coverage_name.split("(")[0].strip() or coverage_name
    return canonicalize_coverage_name(base_name).normalized_key


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
