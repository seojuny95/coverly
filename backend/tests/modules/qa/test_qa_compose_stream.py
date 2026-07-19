from app.modules.qa.agent.compose_stream import sentence_verified_deltas


def _run(tokens: list[str], amounts: dict[str, str], sources: list[str]) -> str:
    return "".join(sentence_verified_deltas(iter(tokens), amounts, sources))


def test_placeholder_is_substituted_with_confirmed_amount() -> None:
    out = _run(["암진단비는 ", "{{amt1}}", "이 ", "있어요."], {"amt1": "3,000만원"}, [])
    assert out == "암진단비는 3,000만원이 있어요."


def test_quoted_number_grounded_in_sources_is_released() -> None:
    out = _run(["대기기간은 ", "90일", "이에요."], {}, ["대기기간 90일"])
    assert "90일" in out


def test_ungrounded_raw_number_sentence_is_withheld() -> None:
    out = _run(["합계는 ", "9,999만원", "이에요."], {"amt1": "3,000만원"}, [])
    assert "9,999" not in out  # ungrounded raw number -> sentence withheld


def test_unknown_placeholder_sentence_is_withheld() -> None:
    out = _run(["금액은 ", "{{amtX}}", "이에요."], {"amt1": "3,000만원"}, [])
    assert "amtX" not in out and "{{" not in out


def test_trailing_text_without_terminator_is_flushed() -> None:
    out = _run(["안녕하세요"], {}, [])
    assert out == "안녕하세요"


# --- Extra adversarial tests (safety boundary hardening) ---


def test_placeholder_split_across_tokens_is_buffered() -> None:
    # A single {{amt1}} arrives as three separate tokens.
    out = _run(["보장은 ", "{{", "amt1", "}}", "이에요."], {"amt1": "5,000만원"}, [])
    assert out == "보장은 5,000만원이에요."


def test_multiple_sentences_in_one_buffer_all_released() -> None:
    out = _run(
        ["암진단비는 {{amt1}}이에요. 대기기간은 90일이에요."],
        {"amt1": "3,000만원"},
        ["대기기간 90일"],
    )
    assert out == "암진단비는 3,000만원이에요. 대기기간은 90일이에요."


def test_valid_sentence_released_then_ungrounded_withheld() -> None:
    out = _run(
        ["대기기간은 90일이에요. ", "그리고 합계는 9,999만원이에요."],
        {},
        ["대기기간 90일"],
    )
    assert "대기기간은 90일이에요." in out
    assert "9,999" not in out


def test_mixed_placeholder_and_quoted_number_both_verified() -> None:
    out = _run(
        ["암진단비 ", "{{amt1}}", "에 대기기간 ", "90일", "이에요."],
        {"amt1": "3,000만원"},
        ["대기기간 90일"],
    )
    assert out == "암진단비 3,000만원에 대기기간 90일이에요."


def test_mixed_placeholder_ok_but_raw_number_ungrounded_withholds_whole() -> None:
    # Placeholder is fine, but an extra ungrounded raw number taints the sentence.
    out = _run(
        ["암진단비 {{amt1}}에 무슨 9,999만원이 있어요."],
        {"amt1": "3,000만원"},
        [],
    )
    assert out == ""


def test_newline_is_a_sentence_boundary() -> None:
    out = _run(["첫 줄이에요\n", "둘째 줄 대기기간 90일이에요."], {}, ["대기기간 90일"])
    assert out.startswith("첫 줄이에요\n")


def test_empty_stream_yields_nothing() -> None:
    out = _run([], {}, [])
    assert out == ""


def test_unknown_placeholder_in_second_sentence_only_withholds_second() -> None:
    out = _run(
        ["대기기간은 90일이에요. 금액은 {{amtX}}이에요."],
        {"amt1": "3,000만원"},
        ["대기기간 90일"],
    )
    assert "대기기간은 90일이에요." in out
    assert "amtX" not in out and "{{" not in out


# --- Residual-digit fail-closed guard (foreign-unit / bare-number escapes) ---


def test_foreign_currency_unit_ungrounded_is_withheld() -> None:
    # 5000달러 is not Korean MONEY nor a known counter -> escapes grounding,
    # but the residual-digit guard must withhold it (no source for 5000).
    out = _run(["보험금은 ", "5000달러", "예요."], {}, [])
    assert "5000" not in out and out == ""


def test_person_counter_ungrounded_is_withheld() -> None:
    # 명 is not in the counter list -> 9999 escapes grounding; must be withheld.
    out = _run(["가입자는 ", "9999명", "이에요."], {}, [])
    assert "9999" not in out and out == ""


def test_bare_number_without_unit_ungrounded_is_withheld() -> None:
    # A bare number with no unit at all escapes grounding; must be withheld.
    out = _run(["합계는 ", "9,999", "예요."], {}, [])
    assert "9,999" not in out and "9999" not in out and out == ""


def test_placeholder_value_with_odd_shape_still_released() -> None:
    # Substituted placeholder value lives in amounts.values() -> residual digits
    # of the released value must not trip the guard.
    out = _run(["보험금은 ", "{{amt1}}", "예요."], {"amt1": "5000달러"}, [])
    assert out == "보험금은 5000달러예요."


def test_quoted_foreign_unit_present_in_sources_is_released() -> None:
    # The odd-unit number is verbatim in grounding_sources -> released.
    out = _run(["보장한도는 ", "5000달러", "예요."], {}, ["보장한도 5000달러"])
    assert out == "보장한도는 5000달러예요."


def test_quoted_person_counter_present_in_sources_is_released() -> None:
    out = _run(["가입자는 ", "9999명", "이에요."], {}, ["가입자 9999명"])
    assert out == "가입자는 9999명이에요."


def test_bare_digit_substring_of_grounded_number_is_withheld() -> None:
    # 3000 is a digit-substring of the grounded 30,000,000 but was never
    # itself confirmed -> the residual-digit guard must withhold it, not
    # release it via substring matching.
    out = _run(["합계는 ", "3000", "이에요."], {}, ["보장한도 30,000,000원"])
    assert "3000" not in out and out == ""


def test_decimal_substring_of_grounded_number_is_withheld() -> None:
    # 3.5 is a digit-substring of the grounded 13.5 but was never itself
    # confirmed -> must be withheld, not released via substring matching.
    out = _run(["이율은 ", "3.5%", "예요."], {}, ["공시이율 13.5%"])
    assert "3.5" not in out and out == ""
