"""Deterministic policy inventory facts for counsel."""

from pydantic import BaseModel

from app.modules.portfolio.schemas import PolicyInfoInput, PolicyInput


class PolicyFact(BaseModel):
    policy_id: str | None
    분석상태: str | None = None
    기본정보: PolicyInfoInput


class PolicyListResult(BaseModel):
    policies: list[PolicyFact]
    count: int


def list_policy_facts(policies: list[PolicyInput]) -> PolicyListResult:
    """Return basic information for every uploaded policy."""

    facts = [
        PolicyFact(
            policy_id=policy.id,
            분석상태=policy.분석상태,
            기본정보=policy.기본정보,
        )
        for policy in policies
    ]
    return PolicyListResult(policies=facts, count=len(facts))
