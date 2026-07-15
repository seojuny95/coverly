from app.modules.portfolio.premium import summarize_premiums
from app.modules.portfolio.schemas import PolicyInput


def _policy(policy_id: str, premium: dict[str, object] | None) -> PolicyInput:
    기본정보: dict[str, object] = {"보험사": f"보험사-{policy_id}", "상품명": f"상품-{policy_id}"}
    if premium is not None:
        기본정보["보험료"] = premium
    return PolicyInput.model_validate({"id": policy_id, "기본정보": 기본정보, "보장목록": []})


def test_sums_only_monthly_premiums_and_flags_the_rest() -> None:
    policies = [
        _policy("p1", {"금액": 30000, "납입주기": "월납"}),
        _policy("p2", {"금액": 50000, "납입주기": "월납"}),
        _policy("p3", {"금액": 600000, "납입주기": "연납"}),
        _policy("p4", None),
    ]

    overview = summarize_premiums(policies)

    assert overview.monthly_total == 80000
    assert overview.monthly_policy_count == 2
    assert overview.unconfirmed_policy_count == 2
    assert overview.items[2].monthly_amount is None
    assert overview.items[2].cycle == "연납"
