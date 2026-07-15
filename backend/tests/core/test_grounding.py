from app.core.grounding import AMOUNT_UNVERIFIED, normalize_amount, wording_grounded

MAN_UNIT_SOURCE = "| 보장명 | 가입금액 (만원) |\n| --- | --- |\n| 암진단비 | 3,000 |"
WON_SOURCE = "| 보장명 | 가입금액 |\n| --- | --- |\n| 상해사망 | 10,000,000원 |"


def test_amount_absent_from_source_is_demoted() -> None:
    assert normalize_amount("9,999만원", source="암진단비 3,000만원") == AMOUNT_UNVERIFIED


def test_amount_present_is_kept_verbatim() -> None:
    assert normalize_amount("3,000만원", source="암진단비 3,000만원") == "3,000만원"


def test_wording_absent_from_source_is_not_grounded() -> None:
    assert wording_grounded("지어낸 문구", source="실제 원문") is False


def test_wording_present_ignoring_whitespace_is_grounded() -> None:
    assert wording_grounded("암 진단시 지급", source="암진단시\n지급") is True


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


def test_amount_demoted_when_only_a_digit_substring_matches() -> None:
    # The value's digits appear only as a substring across other amounts, never as
    # a real amount. Grounding must compare the value+unit, not a concatenated
    # digit blob, so these hallucinations are demoted (not shown as authoritative).
    assert normalize_amount("23원", "가입금액 12원 34원") == AMOUNT_UNVERIFIED
    assert normalize_amount("500원", "50원 00원") == AMOUNT_UNVERIFIED


def test_amount_grounded_by_exact_number_token_despite_unit_difference() -> None:
    # Source cell is bare "10,000,000"; the LLM returned it with a 원 unit. The
    # exact number token still grounds it — don't over-demote a real amount just
    # because the unit char differs from the source.
    assert normalize_amount("10,000,000원", "| 상해사망 | 10,000,000 |") == "10,000,000원"


def test_manwon_unit_applied_when_source_is_uniformly_manwon() -> None:
    # NH-style: 만원 header, bare cells, no explicitly-united amounts.
    source = (
        "| 보장명 | 가입금액 (만원) |\n| --- | --- |\n| 암진단비 | 3,000 |\n| 상해입원일당 | 100 |"
    )
    assert normalize_amount("3,000", source) == "3,000만원"


def test_bare_amount_not_suffixed_when_source_mixes_units() -> None:
    # One table declares 만원; another carries an explicit 원 amount. A bare value
    # must NOT be assumed 만원 (would be 10,000x wrong) — keep it verbatim.
    source = (
        "| 보장명 | 가입금액 (만원) |\n| --- | --- |\n| 암진단비 | 3,000 |\n\n"
        "| 보장명 | 가입금액 |\n| --- | --- |\n| 실손입원 | 50,000,000원 |\n| 기타 | 5000 |"
    )
    assert normalize_amount("5000", source) == "5000"  # not "5,000만원"
    assert normalize_amount("50,000,000원", source) == "50,000,000원"
