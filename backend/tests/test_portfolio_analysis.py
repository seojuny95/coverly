from app.schemas.portfolio import PolicyInput
from app.services.portfolio_analysis import analyze_portfolio


def _policy(policy_id: str, classification: str, coverage_name: str, amount: str) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": policy_id,
            "기본정보": {
                "보험사": "테스트보험",
                "상품명": f"상품-{policy_id}",
                "보험분류": classification,
            },
            "보장목록": [
                {
                    "담보명": coverage_name,
                    "가입금액": amount,
                    "지급유형": "정액",
                }
            ],
        }
    )


def test_analysis_returns_overall_and_classification_facts() -> None:
    policies = [
        _policy("p1", "질병", "암진단비", "3,000만원"),
        _policy("p2", "상해", "상해수술비", "100만원"),
    ]

    result = analyze_portfolio(policies)

    assert result.status == "complete"
    assert result.policy_count == 2
    assert result.classification_count == 2
    assert result.confirmed_total_amount == 31_000_000
    assert [(item.classification, item.policy_count) for item in result.classifications] == [
        ("상해", 1),
        ("질병", 1),
    ]
    assert {source.policy_id for source in result.sources} == {"p1", "p2"}


def test_analysis_honestly_reports_partial_and_empty_states() -> None:
    partial = PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {"보험분류": "질병"},
            "보장목록": [{"담보명": "알 수 없는 담보", "가입금액": "별도 약정"}],
        }
    )

    partial_result = analyze_portfolio([partial])
    empty_result = analyze_portfolio([])

    assert partial_result.status == "partial"
    assert partial_result.excluded_coverage_count == 1
    assert partial_result.notices
    assert empty_result.status == "empty"
    assert empty_result.policy_count == 0


def test_analysis_inherits_partial_parse_status() -> None:
    policy = _policy("p1", "질병", "암진단비", "3,000만원")
    policy.분석상태 = "부분"

    result = analyze_portfolio([policy])

    assert result.status == "partial"


def test_analysis_does_not_make_adequacy_claims() -> None:
    result = analyze_portfolio([_policy("p1", "질병", "암진단비", "3,000만원")])
    serialized = result.model_dump_json()

    assert "충분" not in serialized
    assert "부족" not in serialized
    assert "적정" not in serialized
