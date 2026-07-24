from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.summary import (
    build_portfolio_facts,
    duplicate_actual_loss_coverage_names,
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
            "실손의료보험",
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
    assert result.claim_channels.medical_indemnity is not None
    assert result.claim_channels.medical_indemnity.name == "실손24"


def test_counts_distinct_actual_loss_coverages_duplicated_across_contracts() -> None:
    policies = [
        _policy("p1", "실손", "보험사A", [{"담보명": "실손의료비", "지급유형": "실손"}]),
        _policy("p2", "실손", "보험사B", [{"담보명": "실손의료비", "지급유형": "실손"}]),
        _policy("p3", "실손", "보험사A", [{"담보명": "실손의료비", "지급유형": "실손"}]),
    ]

    summary = summarize_portfolio_coverages(policies)

    # Three rows represent one coverage name repeated across contracts.
    assert duplicate_actual_loss_coverage_names(summary) == ["실손의료비"]


def test_actual_loss_held_in_one_contract_is_not_counted_as_duplicate() -> None:
    policies = [
        _policy("p1", "실손", "보험사A", [{"담보명": "실손의료비", "지급유형": "실손"}]),
    ]

    summary = summarize_portfolio_coverages(policies)

    assert duplicate_actual_loss_coverage_names(summary) == []


def test_same_actual_loss_name_in_different_domains_is_not_a_duplicate() -> None:
    policies = [
        _policy(
            "health",
            "제3보험",
            "보험사A",
            [{"담보명": "질병입원의료비", "지급유형": "실손"}],
        ),
        _policy(
            "travel",
            "손해보험",
            "보험사B",
            [{"담보명": "질병입원의료비", "지급유형": "실손"}],
            tags=["여행자보험"],
        ),
    ]

    summary = summarize_portfolio_coverages(policies)

    assert {item.coverage_domain for item in summary.actual_loss_coverages} == {
        "medical_expense",
        "travel_medical_expense",
    }
    assert not any(item.duplicate_across_contracts for item in summary.actual_loss_coverages)
    assert duplicate_actual_loss_coverage_names(summary) == []


def test_actual_loss_duplicate_check_includes_damage_coverages_at_same_insurer() -> None:
    policies = [
        _policy(
            "driver-1",
            "손해보험",
            "보험사A",
            [{"담보명": "자동차사고벌금(실손)", "지급유형": "실손"}],
            tags=["운전자보험"],
        ),
        _policy(
            "driver-2",
            "손해보험",
            "보험사A",
            [{"담보명": "자동차사고벌금(실손)", "지급유형": "실손"}],
            tags=["운전자보험"],
        ),
    ]

    summary = summarize_portfolio_coverages(policies)

    assert duplicate_actual_loss_coverage_names(summary) == ["자동차사고벌금(실손)"]
    assert all(item.duplicate_across_contracts for item in summary.actual_loss_coverages)
    assert not any(item.is_medical_indemnity for item in summary.actual_loss_coverages)


def test_travel_medical_actual_loss_does_not_count_as_personal_medical_indemnity() -> None:
    policy = _policy(
        "travel",
        "손해보험",
        "삼성화재",
        [{"담보명": "해외의료비(실손)", "지급유형": "실손"}],
        tags=["여행자보험"],
    )

    summary = summarize_portfolio_coverages([policy])
    medical_item = next(
        item for item in summary.essential_coverage_check.items if item.kind == "medical_indemnity"
    )

    assert summary.actual_loss_coverages[0].coverage_domain == "travel_medical_expense"
    assert summary.actual_loss_coverages[0].is_medical_indemnity is False
    assert medical_item.status == "not_found"
    assert summary.claim_channels is not None
    assert summary.claim_channels.medical_indemnity is not None
    assert summary.claim_channels.medical_indemnity.name == "실손24"
    assert summary.claim_channels.medical_indemnity.links
    assert summary.claim_channels.medical_indemnity.links[0].url == "https://www.silson24.or.kr"


def test_domestic_travel_medical_actual_loss_is_not_personal_medical_indemnity() -> None:
    policy = _policy(
        "travel",
        "손해보험",
        "삼성화재",
        [{"담보명": "국내질병입원의료비", "지급유형": "실손"}],
        tags=["여행자보험"],
    )

    summary = summarize_portfolio_coverages([policy])
    medical_item = next(
        item for item in summary.essential_coverage_check.items if item.kind == "medical_indemnity"
    )

    assert summary.actual_loss_coverages[0].coverage_domain == "travel_medical_expense"
    assert summary.actual_loss_coverages[0].is_medical_indemnity is False
    assert medical_item.status == "not_found"
    assert summary.claim_channels is not None
    assert summary.claim_channels.medical_indemnity is not None
    assert summary.claim_channels.medical_indemnity.name == "실손24"
    assert summary.claim_channels.medical_indemnity.links
    assert summary.claim_channels.medical_indemnity.links[0].url == "https://www.silson24.or.kr"
