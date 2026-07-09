from app.services.coverage.amount import AMOUNT_UNVERIFIED, normalize_amount

MAN_UNIT_SOURCE = "| 보장명 | 가입금액 (만원) |\n| --- | --- |\n| 암진단비 | 3,000 |"
WON_SOURCE = "| 보장명 | 가입금액 |\n| --- | --- |\n| 상해사망 | 10,000,000원 |"


def test_amount_kept_when_grounded_in_source() -> None:
    assert normalize_amount("10,000,000원", WON_SOURCE) == "10,000,000원"


def test_amount_demoted_when_not_in_source() -> None:
    # 99,999,999 appears nowhere in the source digits -> likely hallucinated.
    assert normalize_amount("99,999,999원", WON_SOURCE) == AMOUNT_UNVERIFIED


def test_empty_amount_demoted() -> None:
    assert normalize_amount("", WON_SOURCE) == AMOUNT_UNVERIFIED
    assert normalize_amount("   ", WON_SOURCE) == AMOUNT_UNVERIFIED


def test_non_numeric_amount_passes_grounding() -> None:
    # 무한/한도-style values carry no digits to verify; keep them verbatim.
    assert normalize_amount("무한", WON_SOURCE) == "무한"


def test_bare_amount_under_man_unit_header_gets_explicit_unit() -> None:
    assert normalize_amount("3,000", MAN_UNIT_SOURCE) == "3,000만원"


def test_amount_with_unit_is_not_reformatted() -> None:
    source = MAN_UNIT_SOURCE + "\n| 상해사망 | 1억원 |"
    assert normalize_amount("1억원", source) == "1억원"


def test_grounding_ignores_commas_and_whitespace() -> None:
    source = "| 보장명 | 가입금액 |\n| --- | --- |\n| 상해사망 | 10000000원 |"
    assert normalize_amount("10,000,000원", source) == "10,000,000원"
