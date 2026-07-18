import pytest

from app.modules.portfolio.damage_classification import (
    auto_policy_match_source,
    damage_insurance_type,
    is_auto_policy,
    is_fire_policy,
)
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.special_policies import build_special_policy_analyses


def _policy(
    *,
    category: str,
    product: str = "일반 상품",
    tags: list[str] | None = None,
    coverage_names: list[str] | None = None,
) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "기본정보": {
                "보험분류": category,
                "상품명": product,
                "상품태그": tags or [],
            },
            "보장목록": [
                {"담보명": name, "가입금액": "", "지급유형": "실손"}
                for name in coverage_names or []
            ],
        }
    )


@pytest.mark.parametrize(
    "policy",
    [
        _policy(category="자동차보험"),
        _policy(category="손해보험", product="개인용자동차종합보장"),
        _policy(category="손해보험", tags=["자동차보험"]),
    ],
)
def test_auto_identity_is_shared_by_boolean_and_damage_type(policy: PolicyInput) -> None:
    assert auto_policy_match_source(policy) == "identity"
    assert is_auto_policy(policy) is True
    assert damage_insurance_type(policy) == "자동차보험"


def test_auto_specific_coverage_requires_damage_policy_context() -> None:
    damage_policy = _policy(category="손해보험", coverage_names=["자기차량손해"])
    non_damage_policy = _policy(category="질병보험", coverage_names=["자기차량손해"])

    assert auto_policy_match_source(damage_policy) == "coverage"
    assert is_auto_policy(damage_policy) is True
    assert is_auto_policy(non_damage_policy) is False


def test_driver_legal_cost_coverage_is_not_misclassified_as_auto() -> None:
    policy = _policy(
        category="손해보험",
        tags=["운전자보험"],
        coverage_names=["자동차사고변호사선임비용"],
    )

    assert is_auto_policy(policy) is False
    assert damage_insurance_type(policy) == "운전자보험"


@pytest.mark.parametrize(
    "policy",
    [
        _policy(category="화재보험"),
        _policy(category="손해보험", product="우리집 주택종합보험"),
        _policy(category="손해보험", tags=["주택화재보험"]),
        _policy(category="손해보험", coverage_names=["잔존물제거비용"]),
    ],
)
def test_fire_identity_is_shared_by_analysis_and_damage_type(policy: PolicyInput) -> None:
    analyses = build_special_policy_analyses([policy])

    assert is_fire_policy(policy) is True
    assert damage_insurance_type(policy) == "화재보험"
    assert any(item.kind == "fire" for item in analyses)


def test_fire_coverage_requires_damage_policy_context() -> None:
    policy = _policy(category="질병보험", coverage_names=["잔존물제거비용"])

    assert is_fire_policy(policy) is False
    assert all(item.kind != "fire" for item in build_special_policy_analyses([policy]))
