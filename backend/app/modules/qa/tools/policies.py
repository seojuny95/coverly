"""Agent SDK tools for policy inventory and broad portfolio inspection."""

from agents import RunContextWrapper, function_tool

from app.modules.consultation.contracts import ConsultationEvidence
from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent.contracts import GroundedToolAnswer, QaAgentDependencies
from app.modules.qa.response_support import standard_limitations, with_demographics
from app.modules.qa.schemas import PortfolioQuestionResponse
from app.modules.qa.tools.evidence import portfolio_snapshot_evidence
from app.modules.qa.tools.responses import portfolio_response


@function_tool
def list_policies(wrapper: RunContextWrapper[QaAgentDependencies]) -> GroundedToolAnswer:
    """List every uploaded policy, including auto and other damage classifications."""

    dependencies = wrapper.context
    context = dependencies.context
    if not context.policies:
        return dependencies.unmatched("policies", "No uploaded policies were available.")

    evidence = tuple(_policy_evidence(context.policies))
    answer = f"업로드된 보험은 총 {len(context.policies)}건입니다.\n\n" + "\n".join(
        f"- {item.fact}" for item in evidence
    )
    return dependencies.register(
        "policies",
        portfolio_response(context, answer, evidence),
        evidence=evidence,
        trust_level="deterministic",
    )


@function_tool
def inspect_portfolio(
    wrapper: RunContextWrapper[QaAgentDependencies],
) -> GroundedToolAnswer:
    """Load a bounded portfolio snapshot for broad comparison or counseling."""

    dependencies = wrapper.context
    context = dependencies.context
    evidence = portfolio_snapshot_evidence(context)
    if not evidence:
        return dependencies.unmatched("consultation", "No portfolio evidence was available.")
    response = PortfolioQuestionResponse(
        status="answered",
        answer="제공된 evidence 중 질문에 직접 필요한 항목만 골라 답하세요.",
        citations=[],
        limitations=standard_limitations(context.facts),
        suggestions=[],
    )
    return dependencies.register(
        "consultation",
        with_demographics(response, context.insured),
        evidence=evidence,
    )


def _policy_evidence(policies: list[PolicyInput]) -> list[ConsultationEvidence]:
    evidence: list[ConsultationEvidence] = []
    for index, policy in enumerate(policies, start=1):
        insurer = policy.기본정보.보험사
        product = policy.기본정보.상품명
        classification = policy.기본정보.보험분류 or "미분류"
        label = " · ".join(value for value in (insurer, product) if value) or "상품 정보 미확인"
        evidence.append(
            ConsultationEvidence(
                id=f"tool-policy:{index}",
                fact=f"{label} ({classification}) 가입 사실 확인",
                policy_id=policy.id,
                insurer=insurer,
                product_name=product,
            )
        )
    return evidence
