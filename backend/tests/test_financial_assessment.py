from app.schemas.portfolio import PolicyInput
from app.services.analysis.financial_assessment import (
    AssessmentContext,
    AssessmentReferenceData,
    CareCostReference,
    IncomeReference,
    MedicalCostReference,
    PortfolioAssessmentFinding,
    assess_portfolio_financials,
)
from app.services.portfolio.premium import summarize_premiums
from app.services.portfolio.summary import build_portfolio_facts


def _policy(
    coverage_name: str,
    amount: str,
    *,
    premium: int = 100_000,
    policy_id: str = "p1",
) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": policy_id,
            "기본정보": {
                "보험사": "테스트보험",
                "상품명": f"테스트상품-{policy_id}",
                "보험분류": "질병",
                "보험료": {"금액": premium, "납입주기": "월납"},
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


def _assess(
    policies: list[PolicyInput],
    *,
    context: AssessmentContext | None = None,
    references: AssessmentReferenceData | None = None,
) -> tuple[PortfolioAssessmentFinding, ...]:
    facts = build_portfolio_facts(policies)
    premium = summarize_premiums(list(facts.policies))
    return assess_portfolio_financials(
        facts,
        premium,
        context=context or AssessmentContext(),
        references=references or AssessmentReferenceData(),
    )


def test_assesses_premium_burden_against_user_income() -> None:
    findings = _assess(
        [_policy("암진단비", "3,000만원", premium=150_000)],
        context=AssessmentContext(monthly_income=3_000_000),
    )

    premium = findings[0]

    assert premium.topic == "premium_burden"
    assert premium.status == "calculated"
    assert premium.confidence == "high"
    assert premium.metrics["burden_percent"] == 5.0
    assert "150,000원 / 3,000,000원" in (premium.calculation or "")


def test_uses_reference_income_only_as_statistical_comparison() -> None:
    findings = _assess(
        [_policy("암진단비", "3,000만원", premium=120_000)],
        references=AssessmentReferenceData(
            income=IncomeReference(
                monthly_income=4_000_000,
                label="KOSIS 성인 가구 월소득",
                source_ids=("kosis-income-2026",),
            )
        ),
    )

    premium = findings[0]

    assert premium.status == "calculated"
    assert premium.confidence == "medium"
    assert premium.evidence_ids == ("kosis-income-2026",)
    assert "통계" in premium.title
    assert premium.metrics["burden_percent"] == 3.0


def test_assesses_diagnosis_coverage_as_living_expense_months() -> None:
    findings = _assess(
        [
            _policy("암진단비", "3,000만원", policy_id="p1"),
            _policy("뇌혈관질환진단비", "2,000만원", policy_id="p2"),
        ],
        context=AssessmentContext(monthly_living_expense=2_000_000),
    )

    diagnosis = findings[1]

    assert diagnosis.topic == "diagnosis_living_months"
    assert diagnosis.status == "calculated"
    assert diagnosis.metrics["diagnosis_total"] == 50_000_000
    assert diagnosis.metrics["covered_months"] == 25.0
    assert "50,000,000원 / 2,000,000원" in (diagnosis.calculation or "")


def test_compares_confirmed_diagnosis_amounts_with_medical_cost_references() -> None:
    findings = _assess(
        [_policy("암진단비", "3,000만원")],
        references=AssessmentReferenceData(
            medical_costs=(
                MedicalCostReference(
                    topic="cancer",
                    label="NHIS 암 입원 진료비 시나리오",
                    patient_cost=8_000_000,
                    non_covered_cost=4_000_000,
                    source_ids=("nhis-cancer-cost", "hira-non-covered"),
                ),
            )
        ),
    )

    medical = findings[2]

    assert medical.topic == "medical_cost_scenario"
    assert medical.status == "calculated"
    assert medical.evidence_ids == ("nhis-cancer-cost", "hira-non-covered")
    assert medical.metrics["cancer_coverage"] == 30_000_000
    assert medical.metrics["cancer_reference_cost"] == 12_000_000
    assert medical.metrics["cancer_difference"] == 18_000_000


def test_death_gap_requires_family_financial_context_before_calculation() -> None:
    needs_context = _assess([_policy("일반상해사망", "1억원")])[3]

    calculated = _assess(
        [_policy("일반상해사망", "1억원")],
        context=AssessmentContext(
            monthly_living_expense=2_500_000,
            dependent_support_months=36,
            debt=50_000_000,
            assets=20_000_000,
        ),
    )[3]

    assert needs_context.status == "needs_context"
    assert "월 생활비" in needs_context.required_context
    assert calculated.status == "calculated"
    assert calculated.metrics["need_before_insurance"] == 120_000_000
    assert calculated.metrics["death_gap"] == 20_000_000
    assert "2,500,000원 × 36개월" in (calculated.calculation or "")


def test_assesses_care_coverage_against_public_copay_scenario() -> None:
    findings = _assess(
        [_policy("장기요양간병비", "1,200만원")],
        references=AssessmentReferenceData(
            care=CareCostReference(
                label="장기요양 시설급여 본인부담 시나리오",
                monthly_total_cost=2_000_000,
                public_copay_rate=0.2,
                source_ids=("nhis-ltc-copay",),
            )
        ),
    )

    care = findings[4]

    assert care.topic == "care_cost_scenario"
    assert care.status == "calculated"
    assert care.evidence_ids == ("nhis-ltc-copay",)
    assert care.metrics["monthly_user_cost"] == 400_000
    assert care.metrics["covered_months"] == 30.0
