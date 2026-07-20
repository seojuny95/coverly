from app.modules.counsel.facts.portfolio import build_portfolio_fact_bundle
from app.modules.portfolio.schemas import PolicyInput


def test_build_portfolio_fact_bundle_is_llm_friendly_and_safe() -> None:
    bundle = build_portfolio_fact_bundle(_portfolio_policies())

    assert bundle.premium.monthly_total == 80_000
    assert bundle.premium.note == "월납으로 확인된 보험료를 합산했어요."
    cancer = next(item for item in bundle.essential_coverages if item.kind == "cancer")
    assert cancer.status_label == "확인됨"
    assert cancer.confirmed_amount == 30_000_000
    medical = next(item for item in bundle.essential_coverages if item.kind == "medical_indemnity")
    assert medical.status_label == "확인 필요"
    assert bundle.actual_loss_duplicates.has_duplicates is True
    assert "질병실손의료비" in bundle.actual_loss_duplicates.duplicate_coverage_names
    assert "해지" in " ".join(bundle.interpretation_rules)
    assert "단정하지 않습니다" in " ".join(bundle.interpretation_rules)


def _portfolio_policies() -> list[PolicyInput]:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {
                    "보험사": "현대해상",
                    "상품명": "건강보험A",
                    "보험료": {"금액": 50_000, "납입주기": "월납"},
                },
                "보장목록": [
                    {
                        "담보명": "일반암진단비",
                        "가입금액": "3,000만원",
                        "가입금액숫자": 30_000_000,
                        "지급유형": "정액",
                    },
                    {
                        "담보명": "질병실손의료비",
                        "가입금액": "실손",
                        "지급유형": "실손",
                    },
                ],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "p2",
                "기본정보": {
                    "보험사": "삼성화재",
                    "상품명": "건강보험B",
                    "보험료": {"금액": 30_000, "납입주기": "월납"},
                },
                "보장목록": [
                    {
                        "담보명": "질병실손의료비",
                        "가입금액": "실손",
                        "지급유형": "실손",
                    }
                ],
            }
        ),
    ]
    return policies
