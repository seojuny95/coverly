import pytest

from app.modules.analysis.summary_overview import (
    SummaryOverviewUnavailableError,
    attach_summary_overview,
    generate_summary_overview,
)
from app.modules.portfolio.schemas import (
    EssentialCoverageCheck,
    EssentialCoverageItem,
    EssentialCoverageKind,
    PolicyInput,
    PortfolioCoverageSummary,
    PremiumBenchmark,
    PremiumBenchmarkSource,
    PremiumOverview,
    ReferenceSource,
)
from app.modules.portfolio.summary import (
    build_portfolio_facts,
    normalize_coverage_name,
    summarize_portfolio_coverages,
)


def _policy(
    policy_id: str,
    category: str,
    insurer: str,
    coverages: list[dict[str, object]],
    tags: list[str] | None = None,
) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": policy_id,
            "기본정보": {
                "보험사": insurer,
                "상품명": f"상품-{policy_id}",
                "보험분류": category,
                "상품태그": tags or [],
            },
            "보장목록": coverages,
        }
    )


def _summary_for_premium_guidance(
    monthly_total: int,
    missing_kinds: set[EssentialCoverageKind],
) -> PortfolioCoverageSummary:
    coverage_source = ReferenceSource(
        label="테스트 출처",
        url="https://example.com",
        published_at="2025-01-01",
        reliability="official",
        caveat="테스트용 출처예요.",
    )
    benchmark_source = PremiumBenchmarkSource(
        label="테스트 출처",
        url="https://example.com",
        published_at="2025-01-01",
        reliability="official",
        caveat="테스트용 출처예요.",
    )
    labels: dict[EssentialCoverageKind, str] = {
        "death": "사망 보장",
        "cancer": "암 진단비",
        "cerebrovascular": "뇌혈관질환 진단비",
        "ischemic_heart": "심장질환 진단비",
        "indemnity": "실손의료보험",
    }
    items = [
        EssentialCoverageItem(
            kind=kind,
            label=label,
            status="not_found" if kind in missing_kinds else "well_prepared",
            confirmed_amount=None if kind in missing_kinds else 10_000_000,
            reference_min_amount=None if kind == "indemnity" else 10_000_000,
            reference_max_amount=None if kind == "indemnity" else 20_000_000,
            reference_basis="테스트 기준",
            reference_sources=[coverage_source],
            coverage_count=0 if kind in missing_kinds else 1,
            detail="테스트 상세",
            matched_coverage_names=[] if kind in missing_kinds else [label],
        )
        for kind, label in labels.items()
    ]
    return PortfolioCoverageSummary(
        totals=[],
        indemnity_coverages=[],
        excluded_coverages=[],
        excluded_auto_policy_count=0,
        essential_coverage_check=EssentialCoverageCheck(items=items),
        premium=PremiumOverview(
            monthly_total=monthly_total,
            monthly_policy_count=1,
            unconfirmed_policy_count=0,
            items=[],
        ),
        premium_benchmark=PremiumBenchmark(
            age_band_label="테스트 연령대",
            min_age=30,
            max_age=39,
            average_monthly_income=2_000_000,
            suggested_min_ratio=0.05,
            suggested_max_ratio=0.10,
            suggested_min_premium=100_000,
            suggested_max_premium=200_000,
            income_source=benchmark_source,
            guide_source=benchmark_source,
        ),
    )


def test_summary_overview_uses_deterministic_judgments_for_llm_copy() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {
                "담보명": "암진단비",
                "가입금액": "3천만원",
                "지급유형": "정액",
            }
        ],
    )
    summary = summarize_portfolio_coverages([policy])

    def complete(_system: str, user: str) -> dict[str, object]:
        assert "confirmed_count" in user
        assert "missing" in user
        assert "takeaways" in user
        return {
            "title": "암 진단비는 보이고, 다른 핵심 보장은 이어서 확인해요",
            "paragraphs": [
                "현재 자료에서는 암 진단비가 확인돼요.",
                "다른 핵심 보장은 현재 자료에서 찾지 못해 추가 확인이 필요해요.",
            ],
        }

    overview = generate_summary_overview(summary, complete)

    assert overview is not None
    assert overview.generation == "llm"
    assert overview.title == "암 진단비는 보이고, 다른 핵심 보장은 이어서 확인해요"
    assert [item.label for item in overview.takeaways] == ["보험료", "보장 구성", "다음 확인"]


def test_summary_overview_failure_is_not_replaced_with_deterministic_copy() -> None:
    summary = summarize_portfolio_coverages(
        [_policy("p1", "건강보험", "보험사A", [{"담보명": "암진단비"}])]
    )

    def fail(_system: str, _user: str) -> dict[str, object]:
        raise RuntimeError("offline")

    with pytest.raises(SummaryOverviewUnavailableError):
        attach_summary_overview(summary, fail)


@pytest.mark.parametrize(
    (
        "monthly_total",
        "missing_kinds",
        "expected_title",
        "expected_detail",
    ),
    [
        (
            90_000,
            set(),
            "보험료는 낮고 핵심 보장은 보여요",
            "좋은 신호",
        ),
        (
            90_000,
            {"death"},
            "보험료는 낮지만 권장보험 점검이 필요해요",
            "권장보험 항목을 먼저 점검",
        ),
        (
            150_000,
            set(),
            "보험료와 핵심 보장이 균형 있게 보여요",
            "세부 약관 조건만 확인",
        ),
        (
            150_000,
            {"death"},
            "보험료는 권장 범위지만 권장보험 점검이 필요해요",
            "보장 구성을 점검",
        ),
        (
            250_000,
            set(),
            "보험료가 권장 범위보다 높아요",
            "가입한 보험과 보장내용을 다시 확인",
        ),
    ],
)
def test_summary_overview_combines_premium_range_with_core_coverage_status(
    monthly_total: int,
    missing_kinds: set[EssentialCoverageKind],
    expected_title: str,
    expected_detail: str,
) -> None:
    summary = _summary_for_premium_guidance(monthly_total, missing_kinds)

    def complete(_system: str, user: str) -> dict[str, object]:
        assert expected_title in user
        assert expected_detail in user
        return {
            "title": "보험료와 핵심 보장을 함께 확인해요",
            "paragraphs": [
                "보험료는 권장 구간과 핵심 보장 확인 상태를 함께 봐야 해요.",
                "업로드한 자료 기준의 1차 해석이므로 약관 조건을 이어서 확인해요.",
            ],
        }

    overview = generate_summary_overview(summary, complete)

    assert overview is not None
    premium_takeaway = overview.takeaways[0]
    assert premium_takeaway.title == expected_title
    assert expected_detail in premium_takeaway.detail


def test_sums_safe_fixed_benefits_and_exposes_composition() -> None:
    policies = [
        _policy(
            "p1",
            "질병보험",
            "보험사A",
            [
                {"담보명": "암 진단비", "가입금액": "1,000만원", "지급유형": "정액"},
                {
                    "담보명": "질병수술비",
                    "가입금액": "",
                    "가입금액숫자": 2_000_000,
                    "지급유형": "정액",
                },
            ],
        ),
        _policy(
            "p2",
            "건강보험",
            "보험사B",
            [{"담보명": "암-진단비", "가입금액": "20,000,000원", "지급유형": "고정액"}],
        ),
    ]

    result = summarize_portfolio_coverages(policies)

    cancer = next(item for item in result.totals if item.normalized_name == "암진단비")
    assert cancer.total_amount == 30_000_000
    assert cancer.major_category == "진단"
    assert [item.policy_id for item in cancer.composition] == ["p1", "p2"]
    assert cancer.composition[0].original_amount == "1,000만원"


def test_treatment_benefits_without_payment_type_are_kept_for_display() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {
                "담보명": "중대한화상및부식치료비",
                "가입금액": "1천만원",
                "보장내용": None,
                "해설": None,
            },
            {
                "담보명": "항암방사선약물치료비(감액없음)",
                "가입금액": "2천만원",
                "보장내용": None,
                "해설": None,
            },
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert {
        (item.coverage_name, item.major_category, item.original_amount)
        for item in result.excluded_coverages
    } == {
        ("중대한화상및부식치료비", "치료", "1천만원"),
        ("항암방사선약물치료비(감액없음)", "치료", "2천만원"),
    }


def test_explicit_fixed_treatment_benefit_is_summed() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {
                "담보명": "항암방사선약물치료비(감액없음)",
                "가입금액": "2천만원",
                "지급유형": "정액",
            }
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals[0].display_name == "항암방사선약물치료비"
    assert result.totals[0].major_category == "치료"
    assert result.totals[0].total_amount == 20_000_000
    assert result.excluded_coverages == []


def test_explicit_indemnity_treatment_benefit_is_never_summed() -> None:
    policy = _policy(
        "p1",
        "실손보험",
        "보험사A",
        [
            {
                "담보명": "질병치료비",
                "가입금액": "5천만원",
                "지급유형": "실손",
            }
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.excluded_coverages == []
    assert result.indemnity_coverages[0].coverage_name == "질병치료비"


def test_medical_expense_without_payment_type_is_kept_for_display() -> None:
    policy = _policy(
        "p1",
        "실손보험",
        "보험사A",
        [{"담보명": "상해입원의료비", "가입금액": "5천만원"}],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.indemnity_coverages == []
    assert result.excluded_coverages[0].coverage_name == "상해입원의료비"
    assert result.excluded_coverages[0].major_category == "치료"


def test_explicit_indemnity_category_classifies_medical_expense() -> None:
    policy = _policy(
        "p1",
        "실손보험",
        "보험사A",
        [
            {
                "담보명": "상해입원의료비",
                "가입금액": "5천만원",
                "보장분류": "실손",
            }
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.excluded_coverages == []
    assert result.indemnity_coverages[0].coverage_name == "상해입원의료비"
    assert result.indemnity_coverages[0].major_category == "치료"


def test_unknown_coverage_is_kept_for_display_under_other() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {
                "담보명": "특정질환보장",
                "가입금액": "1천만원",
                "지급유형": "확인필요",
            }
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.indemnity_coverages == []
    assert result.excluded_coverages[0].coverage_name == "특정질환보장"
    assert result.excluded_coverages[0].major_category == "기타"
    assert result.excluded_coverages[0].original_amount == "1천만원"
    assert result.excluded_coverages[0].insurer == "보험사A"


@pytest.mark.parametrize(
    "payment_type",
    ["비정액", "실손 제외", "실비 미해당", "정액·실손"],
)
def test_negated_or_ambiguous_payment_type_is_never_inferred(
    payment_type: str,
) -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {
                "담보명": "암진단비",
                "가입금액": "3천만원",
                "지급유형": payment_type,
            }
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.indemnity_coverages == []
    assert result.excluded_coverages[0].coverage_name == "암진단비"


@pytest.mark.parametrize(
    ("coverage_name", "coverage_category"),
    [
        ("비실손암진단비", None),
        ("암진단비", "실손 제외"),
        ("암진단비", "실비 미해당"),
    ],
)
def test_negated_indemnity_name_or_category_is_never_inferred(
    coverage_name: str,
    coverage_category: str | None,
) -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {
                "담보명": coverage_name,
                "가입금액": "3천만원",
                "보장분류": coverage_category,
            }
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.indemnity_coverages == []
    assert result.excluded_coverages[0].coverage_name == coverage_name


def test_unknown_amount_is_excluded_instead_of_becoming_zero() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [{"담보명": "암진단비", "가입금액": "가입금액 참조", "지급유형": "정액"}],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.excluded_coverages[0].reason == (
        "가입금액을 숫자로 확인하지 못해 합계에는 더하지 않았어요."
    )


def test_damage_policies_are_listed_separately() -> None:
    policy = _policy(
        "car",
        "손해보험",
        "보험사A",
        [{"담보명": "대인배상Ⅰ", "가입금액": "무한", "지급유형": "실손"}],
        tags=["자동차보험"],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.excluded_coverages == []
    assert result.damage_coverages[0].insurance_type == "자동차보험"
    assert result.damage_coverages[0].policies[0].coverages[0].coverage_name == "대인배상Ⅰ"
    assert result.excluded_auto_policy_count == 1


def test_damage_policy_with_auto_coverages_is_listed_as_auto_without_tags() -> None:
    policy = _policy(
        "car",
        "손해보험",
        "보험사A",
        [
            {"담보명": "대인배상Ⅰ", "가입금액": "무한", "지급유형": "실손"},
            {"담보명": "대물배상", "가입금액": "3억원", "지급유형": "실손"},
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.damage_coverages[0].insurance_type == "자동차보험"
    assert result.excluded_auto_policy_count == 1


def test_driver_policy_is_not_mistaken_for_auto_policy() -> None:
    policy = _policy(
        "driver",
        "손해보험",
        "보험사A",
        [{"담보명": "상해사망", "가입금액": "1억원", "지급유형": "정액"}],
        tags=["운전자보험"],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.damage_coverages[0].insurance_type == "운전자보험"
    assert result.excluded_auto_policy_count == 0


def test_legacy_specific_damage_classification_is_excluded_from_totals() -> None:
    policy = _policy(
        "travel",
        "여행자보험",
        "보험사A",
        [{"담보명": "휴대품손해", "가입금액": "100만원", "지급유형": "실손"}],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.indemnity_coverages == []
    assert result.damage_coverages[0].insurance_type == "여행자보험"


def test_indemnity_is_listed_and_flagged_only_across_insurers() -> None:
    policies = [
        _policy("p1", "건강보험", "보험사A", [{"담보명": "실손 의료비", "가입금액": "5천만원"}]),
        _policy("p2", "건강보험", "보험사B", [{"담보명": "실손-의료비", "가입금액": "5천만원"}]),
        _policy("p3", "건강보험", "보험사A", [{"담보명": "상해실비", "가입금액": "3천만원"}]),
    ]

    result = summarize_portfolio_coverages(policies)

    assert result.totals == []
    duplicates = {
        item.policy_id: item.cross_insurer_duplicate for item in result.indemnity_coverages
    }
    assert duplicates == {"p1": True, "p2": True, "p3": False}
    amounts = {item.policy_id: item.original_amount for item in result.indemnity_coverages}
    assert amounts == {"p1": "5천만원", "p2": "5천만원", "p3": "3천만원"}


def test_essential_coverage_check_scans_every_policy_for_core_coverages() -> None:
    policies = [
        _policy(
            "p1",
            "건강보험",
            "보험사A",
            [
                {"담보명": "일반암진단비", "가입금액": "3천만원", "지급유형": "정액"},
                {"담보명": "유사암진단비", "가입금액": "5백만원", "지급유형": "정액"},
                {
                    "담보명": "뇌혈관질환진단비",
                    "가입금액": "3천만원",
                    "지급유형": "정액",
                },
                {
                    "담보명": "심질환진단비",
                    "가입금액": "2천만원",
                    "지급유형": "정액",
                },
                {"담보명": "질병실손의료비", "가입금액": "", "지급유형": "실손"},
            ],
        ),
        _policy(
            "p2",
            "자동차보험",
            "보험사B",
            [
                {
                    "담보명": "교통상해사망",
                    "가입금액": "1억원",
                    "지급유형": "정액",
                }
            ],
        ),
    ]

    result = summarize_portfolio_coverages(policies)
    items = {item.kind: item for item in result.essential_coverage_check.items}

    assert {kind: item.status for kind, item in items.items()} == {
        "death": "well_prepared",
        "cancer": "well_prepared",
        "cerebrovascular": "well_prepared",
        "ischemic_heart": "well_prepared",
        "indemnity": "well_prepared",
    }
    assert items["death"].matched_coverage_names == ["교통상해사망"]
    assert items["cancer"].confirmed_amount == 35_000_000
    assert items["cancer"].matched_coverage_names == ["유사암진단비", "일반암진단비"]


def test_essential_check_flags_narrow_diagnoses_and_multiple_indemnity_contracts() -> None:
    policies = [
        _policy(
            "p1",
            "건강보험",
            "보험사A",
            [
                {"담보명": "뇌출혈진단비", "가입금액": "5천만원", "지급유형": "정액"},
                {
                    "담보명": "급성심근경색진단비",
                    "가입금액": "5천만원",
                    "지급유형": "정액",
                },
                {"담보명": "질병실손의료비", "가입금액": "", "지급유형": "실손"},
            ],
        ),
        _policy(
            "p2",
            "실손보험",
            "보험사B",
            [{"담보명": "상해실비", "가입금액": "", "지급유형": "실손"}],
        ),
    ]

    result = summarize_portfolio_coverages(policies)
    items = {item.kind: item for item in result.essential_coverage_check.items}

    assert items["death"].status == "not_found"
    assert items["cancer"].status == "not_found"
    assert items["cerebrovascular"].status == "not_found"
    assert items["ischemic_heart"].status == "not_found"
    assert items["indemnity"].status == "needs_review"


def test_essential_indemnity_check_excludes_auto_policy_rows() -> None:
    policy = _policy(
        "auto",
        "자동차보험",
        "보험사A",
        [{"담보명": "자동차상해실손의료비", "가입금액": "", "지급유형": "실손"}],
    )

    result = summarize_portfolio_coverages([policy])
    items = {item.kind: item for item in result.essential_coverage_check.items}

    assert result.indemnity_coverages == []
    assert items["indemnity"].status == "not_found"
    assert items["indemnity"].matched_coverage_names == []


def test_essential_indemnity_check_excludes_auto_fine_actual_loss_terms() -> None:
    policy = _policy(
        "driver",
        "손해보험",
        "보험사A",
        [
            {
                "담보명": "자동차사고벌금(대물, 실손)",
                "가입금액": "500만원",
                "지급유형": "실손",
            }
        ],
        tags=["운전자보험"],
    )

    result = summarize_portfolio_coverages([policy])
    items = {item.kind: item for item in result.essential_coverage_check.items}

    assert result.indemnity_coverages == []
    assert items["indemnity"].status == "not_found"
    assert items["indemnity"].matched_coverage_names == []


def test_essential_indemnity_check_excludes_property_and_driver_actual_loss_terms() -> None:
    policy = _policy(
        "damage",
        "손해보험",
        "보험사A",
        [
            {
                "담보명": "12대가전제품고장수리 비용(실손)",
                "가입금액": "100만원",
                "지급유형": "실손",
            },
            {"담보명": "가족일상생활배상책임(실손)", "가입금액": "1억원", "지급유형": "실손"},
            {"담보명": "북괴,침강및사태손해(실손)", "가입금액": "1억원", "지급유형": "실손"},
            {
                "담보명": "자동차사고변호사선임 비용(특정사고경찰조사 포함)(실손)",
                "가입금액": "500만원",
                "지급유형": "실손",
            },
            {
                "담보명": "주택(화재)가재도구재 조달차액지원(실손)",
                "가입금액": "1천만원",
                "지급유형": "실손",
            },
            {"담보명": "화재(폭발포함)배상책임(실손)", "가입금액": "1억원", "지급유형": "실손"},
            {
                "담보명": "화재손해(폐기물 운반 및 매립·소각 등 비용 포함)(실손)",
                "가입금액": "1억원",
                "지급유형": "실손",
            },
            {"담보명": "고속도로교통상해사망", "가입금액": "1억원", "지급유형": "정액"},
            {"담보명": "상해사망·후유장해 (20-100%)", "가입금액": "1억원", "지급유형": "정액"},
        ],
        tags=["운전자보험", "화재보험"],
    )

    result = summarize_portfolio_coverages([policy])
    items = {item.kind: item for item in result.essential_coverage_check.items}

    assert result.indemnity_coverages == []
    assert items["indemnity"].status == "not_found"
    assert items["indemnity"].coverage_count == 0
    assert items["indemnity"].matched_coverage_names == []


def test_special_policy_analysis_is_returned_only_for_present_policy_types() -> None:
    raw_policies = [
        {
            "id": "auto",
            "기본정보": {
                "보험사": "보험사A",
                "상품명": "개인용 자동차보험",
                "보험분류": "자동차보험",
            },
            "보장목록": [{"담보명": "대인배상Ⅰ", "가입금액": ""}],
        },
        {
            "id": "driver",
            "기본정보": {
                "보험사": "보험사B",
                "상품명": "안심 운전자보험",
                "보험분류": "상해보험",
            },
            "보장목록": [{"담보명": "교통사고처리지원금", "가입금액": "1억원"}],
        },
        {
            "id": "travel",
            "기본정보": {
                "보험사": "보험사C",
                "상품명": "해외여행보험",
                "보험분류": "여행자보험",
            },
            "보장목록": [{"담보명": "해외의료비", "가입금액": "3천만원"}],
        },
        {
            "id": "fire",
            "기본정보": {
                "보험사": "보험사D",
                "상품명": "우리집 화재보험",
                "보험분류": "재산보험",
            },
            "보장목록": [{"담보명": "화재손해", "가입금액": "1억원"}],
        },
    ]
    policies = [PolicyInput.model_validate(policy) for policy in raw_policies]

    result = summarize_portfolio_coverages(policies)

    assert [item.kind for item in result.special_policy_analyses] == [
        "auto",
        "driver",
        "travel",
        "fire",
    ]
    assert result.special_policy_analyses[0].confirmed_coverage_names == ["대인배상Ⅰ"]
    assert result.special_policy_analyses[1].product_names == ["안심 운전자보험"]
    auto_checks = {item.label: item for item in result.special_policy_analyses[0].coverage_checks}
    assert auto_checks["상대방의 신체 피해"].status == "confirmed"
    assert auto_checks["상대방의 재물 피해"].status == "not_found"
    assert auto_checks["상대방의 신체 피해"].matched_coverage_names == ["대인배상Ⅰ"]
    assert "미가입이라고 단정할 수는 없어요" in result.special_policy_analyses[0].overview

    driver_checks = {item.label: item for item in result.special_policy_analyses[1].coverage_checks}
    assert driver_checks["교통사고 처리 지원"].status == "confirmed"
    assert driver_checks["변호사 선임 비용"].status == "not_found"


def test_special_policy_analysis_does_not_treat_insurer_name_as_fire_policy() -> None:
    policy = PolicyInput.model_validate(
        {
            "id": "third",
            "기본정보": {
                "보험사": "흥국화재",
                "상품명": "무배당 흥국화재 맘편한 자녀사랑보험",
                "보험분류": "제3보험",
            },
            "보장목록": [{"담보명": "암진단비", "가입금액": "3천만원", "지급유형": "정액"}],
        }
    )

    result = summarize_portfolio_coverages([policy])

    assert all(item.kind != "fire" for item in result.special_policy_analyses)


def test_special_policy_analysis_infers_auto_from_auto_specific_coverages() -> None:
    policy = _policy(
        "damage",
        "손해보험",
        "보험사A",
        [
            {"담보명": "대인배상Ⅰ", "가입금액": "무한", "지급유형": "실손"},
            {"담보명": "자기차량손해", "가입금액": "차량가액", "지급유형": "실손"},
        ],
    )

    result = summarize_portfolio_coverages([policy])
    analyses = {item.kind: item for item in result.special_policy_analyses}

    assert "auto" in analyses
    checks = {item.label: item for item in analyses["auto"].coverage_checks}
    assert checks["상대방의 신체 피해"].matched_coverage_names == ["대인배상Ⅰ"]
    assert checks["내 차량 손해"].matched_coverage_names == ["자기차량손해"]


def test_special_policy_analysis_can_show_driver_and_fire_for_one_damage_policy() -> None:
    policy = _policy(
        "damage",
        "손해보험",
        "보험사A",
        [
            {"담보명": "자동차사고벌금(대물, 실손)", "가입금액": "500만원", "지급유형": "실손"},
            {"담보명": "화재손해", "가입금액": "1억원", "지급유형": "실손"},
            {"담보명": "화재(폭발포함)배상책임", "가입금액": "1억원", "지급유형": "실손"},
        ],
        tags=["운전자보험"],
    )

    result = summarize_portfolio_coverages([policy])
    analyses = {item.kind: item for item in result.special_policy_analyses}

    assert "driver" in analyses
    assert "fire" in analyses
    assert analyses["fire"].product_names == ["상품-damage"]
    fire_checks = {item.label: item for item in analyses["fire"].coverage_checks}
    assert fire_checks["건물·가재 화재 손해"].matched_coverage_names == ["화재손해"]
    assert fire_checks["화재 배상책임"].matched_coverage_names == ["화재(폭발포함)배상책임"]


def test_premium_summary_includes_auto_policy_premiums() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "health",
                "기본정보": {
                    "보험사": "보험사A",
                    "상품명": "건강보험",
                    "보험분류": "건강보험",
                    "보험료": {"금액": 40_000, "납입주기": "월납"},
                },
                "보장목록": [],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "auto",
                "기본정보": {
                    "보험사": "보험사B",
                    "상품명": "개인용 자동차보험",
                    "보험분류": "자동차보험",
                    "보험료": {"금액": 70_000, "납입주기": "월납"},
                },
                "보장목록": [],
            }
        ),
    ]

    result = summarize_portfolio_coverages(policies)

    assert result.premium is not None
    assert result.premium.monthly_total == 110_000
    assert result.premium.monthly_policy_count == 2


def test_non_medical_indemnity_terms_are_not_listed_as_medical_indemnity() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {
                "담보명": "가족화재벌금(실손)",
                "가입금액": "2천만원",
                "지급유형": "실손",
            }
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.indemnity_coverages == []
    assert result.excluded_coverages[0].coverage_name == "가족화재벌금(실손)"


def test_medical_indemnity_classifier_does_not_treat_income_benefit_as_medical() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [{"담보명": "운전자보험 휴업급여", "가입금액": "100만원", "지급유형": "실손"}],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.indemnity_coverages == []
    assert result.excluded_coverages[0].coverage_name == "운전자보험 휴업급여"


def test_name_normalization_does_not_apply_semantic_aliases() -> None:
    assert normalize_coverage_name(" 암-진단비(일반) ") == "암진단비일반"
    assert normalize_coverage_name("암진단금") != normalize_coverage_name("암진단비")


def test_major_category_does_not_merge_distinct_coverage_names() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {"담보명": "암진단비", "가입금액": "3천만원", "지급유형": "정액"},
            {"담보명": "유사암진단비", "가입금액": "1천만원", "지급유형": "정액"},
            {"담보명": "암수술비", "가입금액": "5백만원", "지급유형": "정액"},
        ],
    )

    result = summarize_portfolio_coverages([policy])

    actual = [(item.display_name, item.major_category, item.total_amount) for item in result.totals]
    assert actual == [
        ("암수술비", "수술", 5_000_000),
        ("암진단비", "진단", 30_000_000),
        ("유사암진단비", "진단", 10_000_000),
    ]


def test_curated_name_variants_merge_with_stable_canonical_display() -> None:
    base_coverages = [
        {"담보명": "뇌혈관질환진단비", "가입금액숫자": 10_000_000, "지급유형": "정액"},
        {
            "담보명": "암진단비(유사암제외)",
            "가입금액숫자": 20_000_000,
            "지급유형": "정액",
        },
        {
            "담보명": "유사암진단비(감액없음)",
            "가입금액숫자": 10_000_000,
            "지급유형": "정액",
        },
        {
            "담보명": "허혈성심장질환진단비",
            "가입금액숫자": 10_000_000,
            "지급유형": "정액",
        },
    ]
    variant_coverages = [
        {
            "담보명": "뇌혈관질환진단비(감액없음)",
            "가입금액숫자": 20_000_000,
            "지급유형": "정액",
        },
        {
            "담보명": "암진단비(유사암제외)(감액없음)",
            "가입금액숫자": 40_000_000,
            "지급유형": "정액",
        },
        {"담보명": "유사암진담비", "가입금액숫자": 20_000_000, "지급유형": "정액"},
        {
            "담보명": "허혈성심질환진단비(감액없음)",
            "가입금액숫자": 20_000_000,
            "지급유형": "정액",
        },
    ]
    policies = [
        _policy("p1", "건강보험", "보험사A", base_coverages),
        _policy("p2", "건강보험", "보험사B", variant_coverages),
    ]

    forward = summarize_portfolio_coverages(policies)
    reverse = summarize_portfolio_coverages(list(reversed(policies)))

    expected = {
        "뇌혈관질환진단비": 30_000_000,
        "암진단비(유사암제외)": 60_000_000,
        "유사암진단비": 30_000_000,
        "허혈성심질환진단비": 30_000_000,
    }
    assert {item.display_name: item.total_amount for item in forward.totals} == expected
    assert {item.display_name: item.total_amount for item in reverse.totals} == expected
    assert forward == reverse
    assert all(item.coverage_count == 2 for item in forward.totals)
    original_names = {
        source.coverage_name for item in forward.totals for source in item.composition
    }
    assert original_names == {coverage["담보명"] for coverage in base_coverages + variant_coverages}


def test_high_similarity_never_overrides_coverage_identity() -> None:
    names = [
        "암진단비",
        "유사암진단비",
        "암수술비",
        "재진단암진단비",
        "상해후유장해",
        "질병후유장해",
        "암진단비(감액50%)",
    ]
    policies = [
        _policy(
            f"p{index}",
            "건강보험",
            f"보험사{index}",
            [{"담보명": name, "가입금액숫자": 1_000_000, "지급유형": "정액"}],
        )
        for index, name in enumerate(names)
    ]

    result = summarize_portfolio_coverages(policies)

    assert len(result.totals) == len(names)
    assert {item.display_name for item in result.totals} == set(names)
    assert all(item.total_amount == 1_000_000 for item in result.totals)


def test_curated_aliases_from_one_insurer_stay_unsummed() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {"담보명": "뇌혈관질환진단비", "가입금액숫자": 10_000_000, "지급유형": "정액"},
            {
                "담보명": "뇌혈관질환진단비(감액없음)",
                "가입금액숫자": 20_000_000,
                "지급유형": "정액",
            },
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert [item.total_amount for item in result.totals] == [10_000_000, 20_000_000]
    assert all(item.coverage_count == 1 for item in result.totals)


def test_repeated_name_from_one_insurer_is_not_summed() -> None:
    policies = [
        _policy(
            "p1",
            "건강보험",
            "보험사A",
            [
                {"담보명": "후유장해", "가입금액": "1천만원", "지급유형": "정액"},
                {"담보명": "후유장해", "가입금액": "2천만원", "지급유형": "정액"},
            ],
        ),
        _policy(
            "p2",
            "건강보험",
            "보험사B",
            [{"담보명": "후유장해", "가입금액": "3천만원", "지급유형": "정액"}],
        ),
    ]

    result = summarize_portfolio_coverages(policies)

    assert [total.total_amount for total in result.totals] == [10_000_000, 20_000_000, 30_000_000]
    assert all(total.coverage_count == 1 for total in result.totals)


def test_build_portfolio_facts_reuses_the_same_summary_contract() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [{"담보명": "암진단비", "가입금액": "1천만원", "지급유형": "정액"}],
    )

    facts = build_portfolio_facts([policy])

    assert facts.policies == (policy,)
    assert facts.coverage_summary.totals[0].total_amount == 10_000_000


def test_summary_includes_claim_channels_for_known_insurers_and_indemnity() -> None:
    policies = [
        _policy(
            "p1",
            "건강보험",
            "삼성화재",
            [{"담보명": "암진단비", "가입금액": "1천만원", "지급유형": "정액"}],
        ),
        _policy(
            "p2",
            "실손보험",
            "메리츠화재",
            [{"담보명": "질병실손의료비", "가입금액": "5천만원", "지급유형": "실손"}],
        ),
    ]

    result = summarize_portfolio_coverages(policies)

    assert result.claim_channels is not None
    assert [insurer.name for insurer in result.claim_channels.insurers] == [
        "삼성화재",
        "메리츠화재",
    ]
    assert result.claim_channels.indemnity is not None
    assert result.claim_channels.indemnity.name == "실손24"


def test_counts_distinct_indemnity_coverages_duplicated_across_insurers() -> None:
    from app.modules.portfolio.summary import count_duplicate_indemnity_coverages

    policies = [
        _policy("p1", "실손", "보험사A", [{"담보명": "실손의료비", "지급유형": "실손"}]),
        _policy("p2", "실손", "보험사B", [{"담보명": "실손의료비", "지급유형": "실손"}]),
        _policy("p3", "실손", "보험사A", [{"담보명": "실손의료비", "지급유형": "실손"}]),
    ]

    summary = summarize_portfolio_coverages(policies)

    # 3 rows, but one distinct coverage name duplicated across insurers -> count 1
    assert count_duplicate_indemnity_coverages(summary) == 1


def test_indemnity_held_at_single_insurer_is_not_counted_as_duplicate() -> None:
    from app.modules.portfolio.summary import count_duplicate_indemnity_coverages

    policies = [
        _policy("p1", "실손", "보험사A", [{"담보명": "실손의료비", "지급유형": "실손"}]),
    ]

    summary = summarize_portfolio_coverages(policies)

    assert count_duplicate_indemnity_coverages(summary) == 0
