"""Agent SDK tools for verified insurance claim channels."""

from agents import RunContextWrapper, function_tool

from app.modules.coverage.matching import canonicalize_coverage_name
from app.modules.portfolio.damage_classification import is_auto_policy
from app.modules.qa.agent.contracts import GroundedToolAnswer, QaAgentDependencies
from app.modules.qa.context import QaContext
from app.modules.qa.response_support import with_demographics
from app.modules.qa.schemas import PortfolioQuestionResponse
from app.modules.reference_data.claim_channels import claim_channel_block


@function_tool
def get_claim_channels(
    wrapper: RunContextWrapper[QaAgentDependencies],
    coverage_names: list[str],
    include_auto_policies: bool = False,
    include_medical_indemnity_service: bool = False,
) -> GroundedToolAnswer:
    """Return verified claim channels for explicitly selected held coverages.

    Args:
        coverage_names: Concrete held coverage names relevant to the claim.
        include_auto_policies: Include only held auto policies when the incident is automotive.
        include_medical_indemnity_service: Include the verified medical-expense claim service.
    """

    dependencies = wrapper.context
    context = dependencies.context
    insurers = _claim_insurers(
        context,
        coverage_names,
        include_auto_policies=include_auto_policies,
        medical_indemnity_only=include_medical_indemnity_service,
    )
    block = claim_channel_block(
        insurers,
        has_medical_indemnity=include_medical_indemnity_service,
    )
    if not block.insurers and block.medical_indemnity is None:
        return dependencies.unmatched(
            "claim_channels",
            "No verified claim channel matched.",
        )

    response = PortfolioQuestionResponse(
        status="answered",
        answer=(
            "청구는 확인된 보험사 앱·홈페이지·고객센터에서 시작할 수 있습니다. "
            "필요 서류와 실제 지급 여부는 사고나 진단 내용 및 약관 심사에 따라 달라집니다."
        ),
        citations=[],
        limitations=["청구 채널만 확인했으며 실제 지급 여부와 지급액은 확정하지 않았습니다."],
        suggestions=[],
        claim_channels=block,
    )
    return dependencies.register(
        "claim_channels",
        with_demographics(response, context.insured),
        trust_level="deterministic",
    )


def _claim_insurers(
    context: QaContext,
    coverage_names: list[str],
    *,
    include_auto_policies: bool,
    medical_indemnity_only: bool,
) -> list[str]:
    requested = {
        canonicalize_coverage_name(name).normalized_key for name in coverage_names if name.strip()
    }
    insurers: list[str] = []
    for policy in context.policies:
        if include_auto_policies != is_auto_policy(policy):
            continue
        if requested and not any(
            canonicalize_coverage_name(coverage.담보명).normalized_key in requested
            for coverage in policy.보장목록
        ):
            continue
        if policy.기본정보.보험사:
            insurers.append(policy.기본정보.보험사)

    if medical_indemnity_only:
        medical_insurers = {
            item.insurer
            for item in context.facts.coverage_summary.actual_loss_coverages
            if item.is_medical_indemnity and item.insurer
        }
        insurers = [insurer for insurer in insurers if insurer in medical_insurers]
        if not insurers:
            insurers = list(medical_insurers)
    return list(dict.fromkeys(insurers))
