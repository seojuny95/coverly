from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.facts.special_policies import build_special_policy_facts


def test_auto_policy_returns_populated_analysis_with_matched_names() -> None:
    bundle = build_special_policy_facts([_auto_policy()])

    assert len(bundle.analyses) == 1
    auto = bundle.analyses[0]
    assert auto.kind == "auto"
    assert auto.label == "자동차보험"
    assert auto.policy_count == 1

    checks = {check.label: check for check in auto.coverage_checks}
    injury = checks["상대방의 신체 피해"]
    assert injury.status == "confirmed"
    assert injury.status_label == "확인됨"
    assert injury.matched_coverage_names == ["대인배상I"]

    vehicle = checks["내 차량 손해"]
    assert vehicle.status == "confirmed"
    assert vehicle.matched_coverage_names == ["자기차량손해"]

    uninsured = checks["무보험차 사고 상해"]
    assert uninsured.status == "not_found"
    assert uninsured.status_label == "현재 자료에서 미확인"
    assert uninsured.matched_coverage_names == []


def test_no_special_policies_returns_empty_analyses_not_placeholder() -> None:
    bundle = build_special_policy_facts([_health_policy()])

    assert bundle.analyses == []
    assert "찾지 못했어요" in bundle.note


def test_only_auto_does_not_fabricate_fire_or_driver() -> None:
    bundle = build_special_policy_facts([_auto_policy()])

    assert [analysis.kind for analysis in bundle.analyses] == ["auto"]


def _auto_policy() -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": "auto-1",
            "기본정보": {
                "보험사": "A화재",
                "상품명": "개인용자동차보험",
                "보험분류": "자동차보험",
            },
            "보장목록": [
                {"담보명": "대인배상I", "가입금액": "무한", "지급유형": "실손"},
                {"담보명": "대물배상", "가입금액": "2억원", "지급유형": "실손"},
                {"담보명": "자기차량손해", "가입금액": "차량가액", "지급유형": "실손"},
            ],
        }
    )


def _health_policy() -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": "health-1",
            "기본정보": {"보험사": "B생명", "상품명": "건강보험", "보험분류": "질병보험"},
            "보장목록": [
                {
                    "담보명": "일반암진단비",
                    "가입금액": "3,000만원",
                    "가입금액숫자": 30_000_000,
                    "지급유형": "정액",
                }
            ],
        }
    )
