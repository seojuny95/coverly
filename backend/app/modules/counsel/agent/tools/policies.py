"""Agent SDK tool for policy inventory."""

from agents import RunContextWrapper, function_tool

from app.modules.counsel.context import CounselContext
from app.modules.counsel.facts import policies as policy_facts
from app.modules.counsel.facts.policies import list_policy_facts

PolicyListResult = policy_facts.PolicyListResult


@function_tool
def list_policies(wrapper: RunContextWrapper[CounselContext]) -> PolicyListResult:
    """사용자 포트폴리오의 모든 증권 기본정보를 개수와 함께 나열합니다."""

    return list_policy_facts(wrapper.context.policies)
