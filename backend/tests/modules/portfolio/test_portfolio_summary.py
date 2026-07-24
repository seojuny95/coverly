import pytest

from app.modules.portfolio.schemas import (
    DeathBenefitGuideInput,
    PolicyInput,
)
from app.modules.portfolio.summary import (
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
        "실손의료보험",
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
    assert result.actual_loss_coverages[0].coverage_name == "질병치료비"
    assert result.actual_loss_coverages[0].is_medical_indemnity is True
    assert result.actual_loss_coverages[0].is_damage_policy is False


def test_non_medical_actual_loss_is_kept_out_of_individual_review_rows() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {
                "담보명": "일상생활배상책임",
                "가입금액": "1억원",
                "지급유형": "실손",
            }
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.excluded_coverages == []
    assert result.actual_loss_coverages[0].coverage_name == "일상생활배상책임"
    assert result.actual_loss_coverages[0].is_medical_indemnity is False
    assert result.actual_loss_coverages[0].is_damage_policy is False


@pytest.mark.parametrize(
    ("coverage_name", "guidance_key", "expected_phrase"),
    [
        ("상해실손의료비", "injury_medical_expense", "상해로 치료받았을 때"),
        ("질병실손의료비", "disease_medical_expense", "질병으로 치료받았을 때"),
        ("일상생활배상책임(실손)", "liability", "타인에게 배상해야 하는 실제 손해"),
        ("가족화재벌금(실손)", "legal_cost", "실제로 발생한 법률 비용"),
    ],
)
def test_actual_loss_guidance_comes_from_server_classification(
    coverage_name: str,
    guidance_key: str,
    expected_phrase: str,
) -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [{"담보명": coverage_name, "지급유형": "실손"}],
    )

    item = summarize_portfolio_coverages([policy]).actual_loss_coverages[0]

    assert item.guidance_key == guidance_key
    assert expected_phrase in item.explanation
    assert item.explanation_basis == "generated_guidance"
    assert "보장돼요" not in item.explanation


def test_medical_expense_without_payment_type_is_kept_for_display() -> None:
    policy = _policy(
        "p1",
        "실손의료보험",
        "보험사A",
        [{"담보명": "상해입원의료비", "가입금액": "5천만원"}],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.actual_loss_coverages == []
    assert result.excluded_coverages[0].coverage_name == "상해입원의료비"
    assert result.excluded_coverages[0].major_category == "치료"


def test_explicit_indemnity_category_classifies_medical_expense() -> None:
    policy = _policy(
        "p1",
        "실손의료보험",
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
    assert result.actual_loss_coverages[0].coverage_name == "상해입원의료비"
    assert result.actual_loss_coverages[0].major_category == "치료"
    assert result.actual_loss_coverages[0].is_medical_indemnity is True


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
    assert result.actual_loss_coverages == []
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
    assert result.actual_loss_coverages == []
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
    assert result.actual_loss_coverages == []
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
    assert len(result.actual_loss_coverages) == 1
    assert result.actual_loss_coverages[0].coverage_domain == "property_damage"
    assert result.actual_loss_coverages[0].is_medical_indemnity is False
    assert result.actual_loss_coverages[0].is_damage_policy is True
    assert result.damage_coverages[0].insurance_type == "여행자보험"


def test_medical_indemnity_is_listed_and_flagged_across_contracts() -> None:
    policies = [
        _policy("p1", "건강보험", "보험사A", [{"담보명": "실손 의료비", "가입금액": "5천만원"}]),
        _policy("p2", "건강보험", "보험사B", [{"담보명": "실손-의료비", "가입금액": "5천만원"}]),
        _policy("p3", "건강보험", "보험사A", [{"담보명": "상해실비", "가입금액": "3천만원"}]),
    ]

    result = summarize_portfolio_coverages(policies)

    assert result.totals == []
    duplicates = {
        item.policy_id: item.duplicate_across_contracts for item in result.actual_loss_coverages
    }
    assert duplicates == {"p1": True, "p2": True, "p3": False}
    amounts = {item.policy_id: item.original_amount for item in result.actual_loss_coverages}
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
        "death": "needs_review",
        "cancer": "well_prepared",
        "cerebrovascular": "well_prepared",
        "ischemic_heart": "well_prepared",
        "medical_indemnity": "well_prepared",
    }
    assert items["death"].matched_coverage_names == ["교통상해사망"]
    assert items["death"].confirmed_amount is None
    assert items["death"].coverage_groups[0].label == "제한적인 사망 담보"
    assert "생활비 공백" in (items["death"].reference_basis or "")
    assert items["death"].reference_sources[0].reliability == "private_guidance"
    assert items["death"].coverage_groups[0].total_amount == 100_000_000
    assert items["cancer"].confirmed_amount == 30_000_000
    assert items["cancer"].reference_sources[0].reliability == "private_guidance"
    assert items["medical_indemnity"].reference_sources[0].label == "실손24 · 서비스 안내"
    assert items["cancer"].matched_coverage_names == ["유사암진단비", "일반암진단비"]
    cancer_groups = {group.label: group for group in items["cancer"].coverage_groups}
    assert cancer_groups["암 진단비"].total_amount == 30_000_000
    assert cancer_groups["유사암 진단비"].total_amount == 5_000_000
    assert items["cerebrovascular"].reference_min_amount == 10_000_000
    assert items["cerebrovascular"].reference_max_amount == 20_000_000
    assert items["ischemic_heart"].reference_min_amount == 10_000_000
    assert items["ischemic_heart"].reference_max_amount == 20_000_000


def test_cancer_check_counts_only_primary_cancer_in_confirmed_amount() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {"담보명": "암진단비(유사암제외)", "가입금액": "3천만원", "지급유형": "정액"},
            {"담보명": "유사암진단비", "가입금액": "5백만원", "지급유형": "정액"},
            {"담보명": "고액암진단비", "가입금액": "1천만원", "지급유형": "정액"},
            {"담보명": "소액암진단비", "가입금액": "2백만원", "지급유형": "정액"},
        ],
    )

    result = summarize_portfolio_coverages([policy])
    cancer = next(item for item in result.essential_coverage_check.items if item.kind == "cancer")
    groups = {group.label: group for group in cancer.coverage_groups}

    assert cancer.confirmed_amount == 30_000_000
    assert cancer.matched_coverage_names == [
        "고액암진단비",
        "소액암진단비",
        "암진단비(유사암제외)",
        "유사암진단비",
    ]
    assert groups["암 진단비"].coverage_names == ["암진단비(유사암제외)"]
    assert groups["암 진단비"].total_amount == 30_000_000
    assert groups["유사암 진단비"].total_amount == 5_000_000
    assert groups["고액암 진단비"].total_amount == 10_000_000
    assert groups["소액암 진단비"].total_amount == 2_000_000


def test_cancer_check_groups_named_similar_cancers_and_ignores_exclusions() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {"담보명": "일반암진단비", "가입금액": "3천만원", "지급유형": "정액"},
            {"담보명": "무배당 유사암 진단비", "가입금액": "5백만원", "지급유형": "정액"},
            {"담보명": "갑상선암진단비", "가입금액": "4백만원", "지급유형": "정액"},
            {"담보명": "기타피부암진단비", "가입금액": "3백만원", "지급유형": "정액"},
            {"담보명": "제자리암진단비", "가입금액": "2백만원", "지급유형": "정액"},
            {"담보명": "경계성종양진단비", "가입금액": "1백만원", "지급유형": "정액"},
            {
                "담보명": "암(유사암제외)진단비",
                "가입금액": "2천만원",
                "지급유형": "정액",
            },
        ],
    )

    result = summarize_portfolio_coverages([policy])
    cancer = next(item for item in result.essential_coverage_check.items if item.kind == "cancer")
    groups = {group.label: group for group in cancer.coverage_groups}

    assert cancer.confirmed_amount == 50_000_000
    assert groups["암 진단비"].coverage_names == ["암(유사암제외)진단비", "일반암진단비"]
    assert groups["유사암 진단비"].coverage_names == [
        "갑상선암진단비",
        "경계성종양진단비",
        "기타피부암진단비",
        "무배당 유사암 진단비",
        "제자리암진단비",
    ]
    assert groups["유사암 진단비"].total_amount == 15_000_000


def test_death_benefit_guide_changes_with_user_context() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [{"담보명": "질병사망", "가입금액": "1억원", "지급유형": "정액"}],
    )

    result = summarize_portfolio_coverages(
        [policy],
        DeathBenefitGuideInput(
            has_dependent_family=True,
            has_minor_children=True,
            has_major_debt=True,
        ),
    )
    death = next(item for item in result.essential_coverage_check.items if item.kind == "death")

    assert death.reference_min_amount == 300_000_000
    assert death.reference_max_amount == 500_000_000
    assert death.reference_amount_label == "3억~5억 원"
    assert death.guidance_situation == "가족 생활비, 자녀 양육비, 대출 부담을 모두 책임지는 경우"
    assert "대출 상환 부담" in (death.guidance_reason or "")
    assert death.detail == "기본 사망 보장이 확인돼요."


def test_death_coverage_groups_primary_accident_and_limited_coverages() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {"담보명": "질병사망", "가입금액": "1억원", "지급유형": "정액"},
            {"담보명": "일반상해사망", "가입금액": "2억원", "지급유형": "정액"},
            {"담보명": "대중교통이용중교통상해사망", "가입금액": "3억원", "지급유형": "정액"},
            {"담보명": "상해후유장해", "가입금액": "5천만원", "지급유형": "정액"},
        ],
    )

    result = summarize_portfolio_coverages([policy])
    death = next(item for item in result.essential_coverage_check.items if item.kind == "death")
    groups = {group.label: group for group in death.coverage_groups}

    assert death.status == "well_prepared"
    assert death.confirmed_amount == 100_000_000
    assert death.matched_coverage_names == [
        "대중교통이용중교통상해사망",
        "일반상해사망",
        "질병사망",
    ]
    assert "상해후유장해" not in death.matched_coverage_names
    assert groups["기본 사망 보장"].coverage_names == ["질병사망"]
    assert groups["기본 사망 보장"].total_amount == 100_000_000
    assert groups["상해 중심 사망 담보"].coverage_names == ["일반상해사망"]
    assert groups["상해 중심 사망 담보"].total_amount == 200_000_000
    assert groups["제한적인 사망 담보"].coverage_names == ["대중교통이용중교통상해사망"]
    assert groups["제한적인 사망 담보"].total_amount == 300_000_000


def test_death_coverage_needs_review_when_only_accident_death_exists() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [{"담보명": "상해사망·후유장해 (20-100%) / 보통약관", "가입금액": "1억원"}],
    )

    result = summarize_portfolio_coverages([policy])
    death = next(item for item in result.essential_coverage_check.items if item.kind == "death")

    assert death.status == "needs_review"
    assert death.confirmed_amount is None
    assert death.coverage_groups[0].label == "상해 중심 사망 담보"
    assert "기본 사망보험과는 범위가 달라요" in death.detail


def test_essential_check_flags_narrow_diagnoses_and_multiple_medical_contracts() -> None:
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
            "실손의료보험",
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
    assert items["medical_indemnity"].status == "needs_review"


def test_essential_medical_indemnity_check_excludes_auto_policy_rows() -> None:
    policy = _policy(
        "auto",
        "자동차보험",
        "보험사A",
        [{"담보명": "자동차상해실손의료비", "가입금액": "", "지급유형": "실손"}],
    )

    result = summarize_portfolio_coverages([policy])
    items = {item.kind: item for item in result.essential_coverage_check.items}

    assert not any(item.is_medical_indemnity for item in result.actual_loss_coverages)
    assert items["medical_indemnity"].status == "not_found"
    assert items["medical_indemnity"].matched_coverage_names == []


def test_essential_medical_indemnity_check_excludes_auto_fine_actual_loss_terms() -> None:
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

    assert not any(item.is_medical_indemnity for item in result.actual_loss_coverages)
    assert items["medical_indemnity"].status == "not_found"
    assert items["medical_indemnity"].matched_coverage_names == []


def test_essential_medical_check_excludes_property_and_driver_actual_loss_terms() -> None:
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

    assert not any(item.is_medical_indemnity for item in result.actual_loss_coverages)
    assert items["medical_indemnity"].status == "not_found"
    assert items["medical_indemnity"].coverage_count == 0
    assert items["medical_indemnity"].matched_coverage_names == []
