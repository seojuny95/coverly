from pytest import MonkeyPatch

from app.modules.counsel.facts.portfolio import build_portfolio_fact_bundle
from app.modules.portfolio.schemas import (
    PolicyInput,
    PolicyInsuredDemographicsInput,
    PremiumBenchmark,
    PremiumBenchmarkSource,
)
from app.modules.reference_data import premium_benchmark as premium_benchmark_module


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


def test_essential_coverage_fact_carries_reference_range_and_sources() -> None:
    bundle = build_portfolio_fact_bundle(_portfolio_policies())

    cancer = next(item for item in bundle.essential_coverages if item.kind == "cancer")
    assert cancer.reference_min_amount == 30_000_000
    assert cancer.reference_max_amount == 50_000_000
    assert cancer.reference_basis is not None
    assert cancer.reference_sources
    source = cancer.reference_sources[0]
    assert source.label
    assert source.reliability in (
        "official",
        "public_research",
        "industry",
        "large_private_analysis",
        "private_guidance",
    )
    assert source.caveat


def test_essential_coverage_fact_does_not_fabricate_a_range_for_medical_indemnity() -> None:
    bundle = build_portfolio_fact_bundle(_portfolio_policies())

    medical = next(item for item in bundle.essential_coverages if item.kind == "medical_indemnity")
    assert medical.reference_min_amount is None
    assert medical.reference_max_amount is None
    assert medical.reference_basis is not None
    assert medical.reference_sources


def test_premium_benchmark_fact_is_attached_when_age_is_known(
    monkeypatch: MonkeyPatch,
) -> None:
    benchmark = PremiumBenchmark(
        age_band_label="30~39세",
        min_age=30,
        max_age=39,
        average_monthly_income=3_860_000,
        suggested_min_ratio=0.05,
        suggested_max_ratio=0.10,
        suggested_min_premium=193_000,
        suggested_max_premium=386_000,
        income_source=PremiumBenchmarkSource(
            label="KOSIS 국가통계포털 · 성별 연령대별 소득",
            url="https://kosis.kr/statHtml/statHtml.do",
            published_at="2025-01-01",
            reliability="official",
            caveat="연령대 평균 소득은 개인 소득과 다를 수 있어요.",
        ),
        guide_source=PremiumBenchmarkSource(
            label="뱅크샐러드 · 나에게 맞는 보험료 계산법",
            url="https://www.banksalad.com/articles/insurance",
            published_at="2025-01-01",
            reliability="private_guidance",
            caveat="월 소득의 5%~10% 범위는 민간 가이드예요. 적정 보험료의 공식 기준은 아니에요.",
        ),
    )
    monkeypatch.setattr(premium_benchmark_module, "_preloaded_benchmarks", (benchmark,))
    monkeypatch.setattr(premium_benchmark_module, "_failure_retry_at", None)
    premium_benchmark_module._cached_premium_benchmark_for_age.cache_clear()

    bundle = build_portfolio_fact_bundle(_portfolio_policies_with_age(35))

    assert bundle.premium.benchmark is not None
    assert bundle.premium.benchmark.age_band_label == "30~39세"
    assert bundle.premium.benchmark.suggested_min_premium == 193_000
    assert bundle.premium.benchmark.suggested_max_premium == 386_000
    assert len(bundle.premium.benchmark.sources) == 2


def test_premium_benchmark_fact_is_absent_when_age_is_unknown(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(premium_benchmark_module, "_preloaded_benchmarks", ())
    monkeypatch.setattr(premium_benchmark_module, "_failure_retry_at", None)
    premium_benchmark_module._cached_premium_benchmark_for_age.cache_clear()

    bundle = build_portfolio_fact_bundle(_portfolio_policies())

    assert bundle.premium.benchmark is None


def _portfolio_policies_with_age(age: int) -> list[PolicyInput]:
    policies = _portfolio_policies()
    demographics = PolicyInsuredDemographicsInput(나이=age, 성별="여성", 생애단계="성인")
    policies[0] = policies[0].model_copy(
        update={
            "기본정보": policies[0].기본정보.model_copy(update={"피보험자정보": demographics}),
        }
    )
    return policies


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
