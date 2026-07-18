from evals.rag.text import missing_term_groups, normalize_whitespace, present_terms


def test_normalize_whitespace_collapses_all_whitespace() -> None:
    assert normalize_whitespace("  보험\n  약관\t확인 ") == "보험 약관 확인"


def test_missing_term_groups_accepts_any_term_in_each_group() -> None:
    groups = (("암 진단", "암진단"), ("입원", "입원비"))

    assert missing_term_groups(groups, "암진단 보장을 확인했어요.") == ("입원 / 입원비",)


def test_present_terms_preserves_original_term_values() -> None:
    assert present_terms(("가입 하세요", "반드시 보장"), "가입 하세요라는 표현") == ("가입 하세요",)
