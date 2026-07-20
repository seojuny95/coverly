from app.modules.counsel.facts.coverages import find_overlapping_coverage_facts
from app.modules.portfolio.schemas import PolicyInput


def _policy(
    policy_id: str, insurer: str, product: str, coverages: list[dict[str, str]]
) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": policy_id,
            "기본정보": {"보험사": insurer, "상품명": product},
            "보장목록": coverages,
        }
    )


def test_one_coverage_split_across_rows_is_not_an_overlap() -> None:
    # A real portfolio carried 화재배상책임 twice inside one policy: once for 대인,
    # once for 대물. That is one coverage written in parts, and reporting it as an
    # overlap tells the user they bought the same protection twice.
    policies = [
        _policy(
            "p1",
            "DB손해보험",
            "무배당 프로미라이프",
            [
                {"담보명": "화재(폭발포함)배상책임(실손)", "가입금액": "대인 1인당 15,000만원"},
                {"담보명": "화재(폭발포함)배상책임(실손)", "가입금액": "대물 1사고당 200,000만원"},
            ],
        ),
    ]

    assert find_overlapping_coverage_facts(policies) == []


def test_the_same_coverage_in_two_contracts_is_an_overlap() -> None:
    policies = [
        _policy(
            "p1", "삼성화재", "실손의료보험", [{"담보명": "실손의료비", "가입금액": "5,000만원"}]
        ),
        _policy(
            "p2", "한화손해보험", "한화실손", [{"담보명": "실손의료비", "가입금액": "3,000만원"}]
        ),
    ]

    overlaps = find_overlapping_coverage_facts(policies)

    assert len(overlaps) == 1
    assert {entry.보험사 for entry in overlaps[0].policies} == {"삼성화재", "한화손해보험"}


def test_notation_differences_do_not_hide_a_real_overlap() -> None:
    # PDF line wrapping splits words, so the same coverage can be spelled
    # differently in two policies.
    policies = [
        _policy(
            "p1",
            "A화재",
            "상품1",
            [{"담보명": "화재(폭발포함)배상책 임(실손)", "가입금액": "1억원"}],
        ),
        _policy(
            "p2",
            "B화재",
            "상품2",
            [{"담보명": "화재(폭발포함)배상책임(실손)", "가입금액": "2억원"}],
        ),
    ]

    assert len(find_overlapping_coverage_facts(policies)) == 1


def test_a_meaningful_qualifier_still_separates_two_coverages() -> None:
    # (감액없음) is a payout condition the shared rules treat as the same coverage,
    # but (유사암제외) changes which cancers pay out, so these stay apart.
    policies = [
        _policy("p1", "A화재", "상품1", [{"담보명": "암진단비", "가입금액": "2,000만원"}]),
        _policy(
            "p2", "B화재", "상품2", [{"담보명": "암진단비(유사암제외)", "가입금액": "3,000만원"}]
        ),
    ]

    assert find_overlapping_coverage_facts(policies) == []


def test_a_payout_condition_suffix_does_not_split_a_real_overlap() -> None:
    policies = [
        _policy("p1", "A화재", "상품1", [{"담보명": "뇌혈관질환진단비", "가입금액": "1,000만원"}]),
        _policy(
            "p2",
            "B화재",
            "상품2",
            [{"담보명": "뇌혈관질환진단비(감액없음)", "가입금액": "2,000만원"}],
        ),
    ]

    assert len(find_overlapping_coverage_facts(policies)) == 1
