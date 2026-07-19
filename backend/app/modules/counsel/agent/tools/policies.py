"""Agent SDK tool for policy inventory."""

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel

from app.modules.counsel.context import CounselContext
from app.modules.portfolio.schemas import PolicyInfoInput


class PolicyListResult(BaseModel):
    policies: list[PolicyInfoInput]
    count: int


@function_tool
def list_policies(wrapper: RunContextWrapper[CounselContext]) -> PolicyListResult:
    """사용자 포트폴리오의 모든 증권 기본정보를 개수와 함께 나열합니다."""

    policies = [policy.기본정보 for policy in wrapper.context.policies]
    return PolicyListResult(policies=policies, count=len(policies))
