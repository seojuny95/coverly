from app.schemas.portfolio import PolicyInput
from app.services.portfolio_summary import (
    build_portfolio_facts,
    normalize_coverage_name,
    summarize_portfolio_coverages,
)


def _policy(
    policy_id: str,
    category: str,
    insurer: str,
    coverages: list[dict[str, object]],
) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": policy_id,
            "기본정보": {
                "보험사": insurer,
                "상품명": f"상품-{policy_id}",
                "보험분류": category,
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
    assert cancer.major_category == "진단비"
    assert [item.policy_id for item in cancer.composition] == ["p1", "p2"]
    assert cancer.composition[0].original_amount == "1,000만원"


def test_current_parse_shape_is_supported_conservatively() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {"담보명": "암진단비", "가입금액": "3천만원", "보장내용": None, "해설": None},
            {"담보명": "골절치료비", "가입금액": "100만원", "보장내용": None, "해설": None},
        ],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals[0].total_amount == 30_000_000
    assert result.excluded_coverages[0].coverage_name == "골절치료비"
    assert result.excluded_coverages[0].reason == "지급유형을 안전하게 확인할 수 없음"


def test_unknown_amount_is_excluded_instead_of_becoming_zero() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [{"담보명": "암진단비", "가입금액": "가입금액 참조", "지급유형": "정액"}],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.excluded_coverages[0].reason == "가입금액을 숫자로 확인할 수 없음"


def test_auto_policies_are_completely_excluded() -> None:
    policy = _policy(
        "car",
        "자동차보험",
        "보험사A",
        [{"담보명": "사망", "가입금액": "1억원", "지급유형": "정액"}],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals == []
    assert result.excluded_coverages == []
    assert result.excluded_auto_policy_count == 1


def test_driver_policy_is_not_mistaken_for_auto_policy() -> None:
    policy = _policy(
        "driver",
        "운전자보험",
        "보험사A",
        [{"담보명": "상해사망", "가입금액": "1억원", "지급유형": "정액"}],
    )

    result = summarize_portfolio_coverages([policy])

    assert result.totals[0].total_amount == 100_000_000
    assert result.excluded_auto_policy_count == 0


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
        ("암수술비", "수술비", 5_000_000),
        ("암진단비", "진단비", 30_000_000),
        ("유사암진단비", "진단비", 10_000_000),
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
