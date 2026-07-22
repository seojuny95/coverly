"""Agent SDK tool for policy inventory."""

from agents import RunContextWrapper, function_tool

from app.modules.qa.context import QaContext
from app.modules.qa.facts import policies as policy_facts


@function_tool
def list_policies(wrapper: RunContextWrapper[QaContext]) -> policy_facts.PolicyListResult:
    """사용자 포트폴리오의 모든 증권 기본정보를 개수와 함께 나열합니다."""

    return policy_facts.list_policy_facts(wrapper.context.policies)
