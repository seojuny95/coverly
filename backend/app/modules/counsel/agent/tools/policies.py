"""Agent SDK tool for policy inventory."""

from agents import RunContextWrapper, function_tool

from app.core.untrusted import strip_injection_markers
from app.modules.counsel.context import CounselContext
from app.modules.counsel.facts import policies as policy_facts
from app.modules.counsel.facts.policies import list_policy_facts

PolicyListResult = policy_facts.PolicyListResult
PolicyFact = policy_facts.PolicyFact


def _strip_free_text_fields(fact: PolicyFact) -> PolicyFact:
    """Sanitize 상품명, the only display-only free text lifted verbatim from a PDF.

    상품명 is not a matching key anywhere downstream, so unlike 담보명/보험사 it
    carries no identity-field rationale for staying unstripped.
    """

    if not fact.기본정보.상품명:
        return fact
    updated_info = fact.기본정보.model_copy(
        update={"상품명": strip_injection_markers(fact.기본정보.상품명)}
    )
    return fact.model_copy(update={"기본정보": updated_info})


@function_tool
def list_policies(wrapper: RunContextWrapper[CounselContext]) -> PolicyListResult:
    """사용자 포트폴리오의 모든 증권 기본정보를 개수와 함께 나열합니다."""

    result = list_policy_facts(wrapper.context.policies)
    stripped_policies = [_strip_free_text_fields(policy) for policy in result.policies]
    return result.model_copy(update={"policies": stripped_policies})
