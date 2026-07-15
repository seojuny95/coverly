"""Resolve trusted insured demographics for portfolio features."""

from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.summary import is_damage_policy
from app.modules.qa.contracts import InsuredDemographics


def resolve_portfolio_demographics(
    policies: list[PolicyInput],
    requested: InsuredDemographics | None,
) -> InsuredDemographics:
    """Prefer consistent policy facts and downgrade unverified client claims."""

    policy_values = {
        (info.나이, info.성별)
        for policy in policies
        if not is_damage_policy(policy)
        if (info := policy.기본정보.피보험자정보) is not None
    }

    if len(policy_values) == 1:
        age, gender = next(iter(policy_values))
        return InsuredDemographics(
            age=age,
            gender=gender,
            source="policy",
            status="verified_policy",
        )

    if len(policy_values) > 1:
        if _is_explicit_user_input(requested):
            assert requested is not None
            return InsuredDemographics(
                age=requested.age,
                gender=requested.gender,
                source="user",
                status="conflict_user_override",
            )
        return InsuredDemographics(source="unknown", status="conflict")

    if _is_explicit_user_input(requested):
        assert requested is not None
        return InsuredDemographics(
            age=requested.age,
            gender=requested.gender,
            source="user",
            status="user_provided",
        )

    return InsuredDemographics(source="unknown", status="missing")


def _is_explicit_user_input(requested: InsuredDemographics | None) -> bool:
    if requested is None or requested.source != "user":
        return False
    return requested.age is not None or requested.gender != "미상"
