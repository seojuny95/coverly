import json

import pytest
from pydantic import ValidationError

from app.schemas.consultation import InsuredDemographics
from app.schemas.portfolio import PolicyInput
from app.services.analysis.service import analyze_portfolio
from app.services.portfolio.demographics import resolve_portfolio_demographics
from app.services.qa.service import answer_portfolio_question


def _policy(
    policy_id: str,
    *,
    age: int | None = None,
    gender: str | None = None,
) -> PolicyInput:
    basic_info: dict[str, object] = {
        "보험사": "테스트보험",
        "상품명": f"상품-{policy_id}",
        "보험분류": "질병",
    }
    if age is not None and gender is not None:
        life_stage = "어린이" if age < 19 else "시니어" if age >= 65 else "성인"
        basic_info["피보험자정보"] = {
            "나이": age,
            "성별": gender,
            "생애단계": life_stage,
        }
    return PolicyInput.model_validate(
        {
            "id": policy_id,
            "기본정보": basic_info,
            "보장목록": [{"담보명": "암진단비", "가입금액": "3천만원", "지급유형": "정액"}],
        }
    )


def test_consistent_policy_demographics_override_client_claim() -> None:
    requested = InsuredDemographics(age=52, gender="남성", source="user")

    resolved = resolve_portfolio_demographics(
        [_policy("p1", age=35, gender="여성")],
        requested,
    )

    assert resolved == InsuredDemographics(
        age=35,
        gender="여성",
        source="policy",
        status="verified_policy",
    )


def test_client_cannot_self_assert_policy_source_without_policy_fact() -> None:
    requested = InsuredDemographics(age=35, gender="여성", source="policy")

    resolved = resolve_portfolio_demographics([_policy("p1")], requested)

    assert resolved == InsuredDemographics(source="unknown", status="missing")


def test_conflicting_policies_require_explicit_user_override() -> None:
    policies = [
        _policy("p1", age=35, gender="여성"),
        _policy("p2", age=41, gender="남성"),
    ]

    unverified = resolve_portfolio_demographics(
        policies,
        InsuredDemographics(age=35, gender="여성", source="policy"),
    )
    user_override = resolve_portfolio_demographics(
        policies,
        InsuredDemographics(age=38, gender="여성", source="user"),
    )

    assert unverified == InsuredDemographics(source="unknown", status="conflict")
    assert user_override == InsuredDemographics(
        age=38,
        gender="여성",
        source="user",
        status="conflict_user_override",
    )


def test_policy_demographic_schema_rejects_invalid_or_inconsistent_values() -> None:
    with pytest.raises(ValidationError):
        PolicyInput.model_validate(
            {
                "기본정보": {
                    "피보험자정보": {
                        "나이": "35",
                        "성별": "여성",
                        "생애단계": "성인",
                    }
                }
            }
        )

    with pytest.raises(ValidationError):
        PolicyInput.model_validate(
            {
                "기본정보": {
                    "피보험자정보": {
                        "나이": 35,
                        "성별": "여성",
                        "생애단계": "시니어",
                    }
                }
            }
        )


def test_analysis_exposes_conflict_in_resolved_demographics_and_notice() -> None:
    policies = [
        _policy("p1", age=35, gender="여성"),
        _policy("p2", age=41, gender="남성"),
    ]

    result = analyze_portfolio(
        policies,
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
    )

    assert result.demographics.status == "conflict"
    assert result.demographics.source == "unknown"
    assert result.age is None
    assert result.life_stage == "미상"
    assert any("서로 달라" in notice for notice in result.notices)


def test_qa_uses_same_policy_verified_demographics_resolver() -> None:
    captured: dict[str, object] = {}

    def complete(_system: str, user: str) -> dict[str, object]:
        captured.update(json.loads(user))
        return {
            "confirmed_fact": "암 진단 담보의 가입 사실을 확인했어요",
            "guidance": "일반 가이드로 생활비와 예산을 함께 비교해 보세요",
            "evidence_ids": ["coverage:1"],
            "suggestions": [],
            "limitations": [],
        }

    result = answer_portfolio_question(
        "상담 전에 무엇을 볼까요?",
        [_policy("p1", age=35, gender="여성")],
        demographics=InsuredDemographics(age=70, gender="남성", source="policy"),
        complete=complete,
    )

    assert captured["demographics"] == {
        "age": 35,
        "gender": "여성",
        "source": "policy",
        "status": "verified_policy",
    }
    assert result.demographics.status == "verified_policy"
    assert result.demographics.age == 35


def test_qa_explains_why_conflicting_demographics_disable_personalization() -> None:
    result = answer_portfolio_question(
        "가입한 보험 목록을 알려줘",
        [
            _policy("p1", age=35, gender="여성"),
            _policy("p2", age=41, gender="남성"),
        ],
        demographics=InsuredDemographics(age=35, gender="여성", source="policy"),
    )

    assert result.demographics.status == "conflict"
    assert result.demographics.source == "unknown"
    assert any("서로 달라" in limitation for limitation in result.limitations)
