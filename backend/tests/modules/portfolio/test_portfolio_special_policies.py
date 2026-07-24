from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.summary import summarize_portfolio_coverages


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
                "보험분류": "손해보험",
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
    assert result.special_policy_analyses[1].classification_reasons == [
        "손해보험 증권 안에서 운전자보험 상품명 또는 태그가 확인돼요."
    ]
    auto_checks = {item.label: item for item in result.special_policy_analyses[0].coverage_checks}
    assert auto_checks["상대방의 신체 피해"].status == "confirmed"
    assert auto_checks["상대방의 재물 피해"].status == "not_found"
    assert auto_checks["상대방의 신체 피해"].matched_coverage_names == ["대인배상Ⅰ"]
    assert "미가입이라고 단정할 수는 없어요" in result.special_policy_analyses[0].overview

    driver_checks = {item.label: item for item in result.special_policy_analyses[1].coverage_checks}
    assert driver_checks["교통사고 처리 지원"].status == "confirmed"
    assert driver_checks["변호사 선임 비용"].status == "not_found"


def test_special_policy_analysis_skips_driver_when_policy_is_not_damage() -> None:
    policy = PolicyInput.model_validate(
        {
            "id": "driver",
            "기본정보": {
                "보험사": "보험사A",
                "상품명": "안심 운전자보험",
                "보험분류": "상해보험",
            },
            "보장목록": [{"담보명": "교통사고처리지원금", "가입금액": "1억원"}],
        }
    )

    result = summarize_portfolio_coverages([policy])

    assert all(item.kind != "driver" for item in result.special_policy_analyses)


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
    assert analyses["auto"].classification_reasons == [
        "손해보험 증권 안에서 대인배상, 대물배상, 자차처럼 자동차보험 담보명이 확인돼요."
    ]


def test_damage_policy_with_auto_product_name_is_listed_as_auto_without_tags() -> None:
    policy = PolicyInput.model_validate(
        {
            "id": "auto",
            "기본정보": {
                "보험사": "보험사A",
                "상품명": "개인용자동차종합보장",
                "보험분류": "손해보험",
            },
            "보장목록": [{"담보명": "기본담보", "가입금액": "", "지급유형": "실손"}],
        }
    )

    result = summarize_portfolio_coverages([policy])

    assert result.damage_coverages[0].insurance_type == "자동차보험"


def test_damage_policy_with_fire_coverages_is_listed_as_fire_without_tags() -> None:
    policy = _policy(
        "fire",
        "손해보험",
        "보험사A",
        [
            {"담보명": "화재(폭발포함)배상책임", "가입금액": "1억원", "지급유형": "실손"},
            {"담보명": "잔존물제거비용", "가입금액": "1천만원", "지급유형": "실손"},
        ],
    )

    result = summarize_portfolio_coverages([policy])
    analyses = {item.kind: item for item in result.special_policy_analyses}

    assert result.damage_coverages[0].insurance_type == "화재보험"
    assert "fire" in analyses
    assert analyses["fire"].classification_reasons == [
        "손해보험 증권 안에서 화재, 주택, 재물 손해 관련 상품명이나 담보명이 확인돼요."
    ]


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


def test_non_medical_actual_loss_is_not_listed_as_medical_indemnity() -> None:
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
    assert result.excluded_coverages == []
    assert result.actual_loss_coverages[0].coverage_name == "가족화재벌금(실손)"
    assert result.actual_loss_coverages[0].is_medical_indemnity is False
    assert result.actual_loss_coverages[0].is_damage_policy is False


def test_medical_indemnity_classifier_does_not_treat_income_benefit_as_medical() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [{"담보명": "운전자보험 휴업급여", "가입금액": "100만원", "지급유형": "실손"}],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.excluded_coverages == []
    assert result.actual_loss_coverages[0].coverage_name == "운전자보험 휴업급여"
    assert result.actual_loss_coverages[0].is_medical_indemnity is False
