import inspect
from datetime import date

import pytest

from app.services import demographics as demographics_module
from app.services.demographics import (
    extract_insured_demographics,
    mask_demographic_identifiers,
)
from app.services.summary import extract_policy_summary

ADULT_BIRTH = "95" + "0524"
YOUNG_ADULT_BIRTH = "05" + "0524"
MINOR_BIRTH = "07" + "0712"
OLDER_HOLDER_BIRTH = "80" + "0101"
INVALID_BIRTH = "99" + "1332"
CLASSIFICATION_BIRTH = "90" + "0101"
FULL_SUFFIX = "123" + "4567"


def test_demographics_has_no_insurer_specific_logic() -> None:
    source = inspect.getsource(demographics_module)
    for forbidden in ("현대해상", "DB손해보험", "NH농협", "흥국화재"):
        assert forbidden not in source


@pytest.mark.parametrize(
    ("code", "expected_age", "expected_gender"),
    [
        ("1", 30, "남성"),
        ("2", 30, "여성"),
        ("3", 20, "남성"),
        ("4", 20, "여성"),
        ("5", 30, "남성"),
        ("6", 30, "여성"),
        ("7", 20, "남성"),
        ("8", 20, "여성"),
    ],
)
def test_extracts_supported_century_and_gender_digits(
    code: str,
    expected_age: int,
    expected_gender: str,
) -> None:
    birth = ADULT_BIRTH if code in {"1", "2", "5", "6"} else YOUNG_ADULT_BIRTH

    result = extract_insured_demographics(
        f"피보험자 가나 ({birth}-{code}******)",
        today=date(2025, 5, 24),
    )

    assert result == {
        "나이": expected_age,
        "성별": expected_gender,
        "생애단계": "성인",
    }


def test_age_is_completed_age_and_changes_on_birthday() -> None:
    before_birthday = extract_insured_demographics(
        f"주민등록번호 {MINOR_BIRTH}-3******",
        today=date(2026, 7, 11),
    )
    on_birthday = extract_insured_demographics(
        f"주민등록번호 {MINOR_BIRTH}-3******",
        today=date(2026, 7, 12),
    )

    assert before_birthday == {"나이": 18, "성별": "남성", "생애단계": "어린이"}
    assert on_birthday == {"나이": 19, "성별": "남성", "생애단계": "성인"}


def test_uses_insured_identifier_when_holder_is_also_present() -> None:
    result = extract_insured_demographics(
        f"""
        계약자 가나 주민등록번호 {OLDER_HOLDER_BIRTH}-1******
        피보험자 마바 주민등록번호 {YOUNG_ADULT_BIRTH}-4******
        """,
        today=date(2025, 5, 24),
    )

    assert result == {"나이": 20, "성별": "여성", "생애단계": "성인"}


def test_does_not_substitute_holder_demographics_for_invalid_insured_id() -> None:
    result = extract_insured_demographics(
        f"""
        계약자 가나 주민등록번호 {OLDER_HOLDER_BIRTH}-1******
        피보험자 마바 주민등록번호 {INVALID_BIRTH}-4******
        """,
        today=date(2026, 7, 11),
    )

    assert result is None


@pytest.mark.parametrize(
    "identifier",
    [
        f"{INVALID_BIRTH}-1******",
        "000230-3******",
        "250229-3******",
        f"{ADULT_BIRTH}-9******",
        f"{ADULT_BIRTH}-0******",
    ],
)
def test_rejects_invalid_dates_and_unsupported_century_digits(identifier: str) -> None:
    assert extract_insured_demographics(identifier, today=date(2026, 7, 11)) is None


def test_rejects_future_and_implausibly_old_birthdates() -> None:
    assert extract_insured_demographics("300101-3******", today=date(2026, 7, 11)) is None
    assert extract_insured_demographics("000101-1******", today=date(2026, 7, 11)) is None


def test_returns_none_without_an_identifier() -> None:
    assert extract_insured_demographics("피보험자 가나") is None


def test_accepts_compact_full_identifier_without_returning_raw_pii() -> None:
    raw_identifier = ADULT_BIRTH + FULL_SUFFIX

    result = extract_insured_demographics(
        f"피보험자 가나 {raw_identifier}",
        today=date(2026, 7, 11),
    )

    assert result == {"나이": 31, "성별": "남성", "생애단계": "성인"}
    assert raw_identifier not in repr(result)
    assert ADULT_BIRTH not in repr(result)


def test_masks_valid_and_invalid_identifier_shapes() -> None:
    valid_full_identifier = f"{ADULT_BIRTH}-{FULL_SUFFIX}"
    invalid_masked_identifier = f"{INVALID_BIRTH}-9******"
    compact_masked_identifier = YOUNG_ADULT_BIRTH + "4123456"
    text = (
        f"정상 {valid_full_identifier} / 오류 {invalid_masked_identifier} / "
        f"압축 {compact_masked_identifier}"
    )

    masked = mask_demographic_identifiers(text)

    assert masked == ("정상 ******-******* / 오류 ******-******* / 압축 ******-*******")
    assert ADULT_BIRTH not in masked
    assert INVALID_BIRTH not in masked
    assert YOUNG_ADULT_BIRTH not in masked


def test_summary_llm_receives_masked_text_but_local_result_keeps_only_safe_fields() -> None:
    raw_identifier = f"{ADULT_BIRTH}-1******"
    received_texts: list[str] = []

    def capture_llm_text(text: str) -> None:
        received_texts.append(text)
        return None

    result = extract_policy_summary(
        f"피보험자: 가나\n주민등록번호: {raw_identifier}",
        llm_extractor=capture_llm_text,
    )

    assert received_texts == ["피보험자: 가나\n주민등록번호: ******-*******"]
    assert raw_identifier not in repr(result)
    assert ADULT_BIRTH not in repr(result)
    assert result["피보험자정보"]["성별"] == "남성"
    assert set(result["피보험자정보"]) == {"나이", "성별", "생애단계"}


def test_summary_classification_receives_masked_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def classify(*, text: str, product_name: str | None) -> dict[str, object]:
        captured["text"] = text
        return {"보험분류": "미분류", "상품태그": []}

    monkeypatch.setattr("app.services.summary.classify_policy", classify)
    extract_policy_summary(
        f"피보험자 가나 ({CLASSIFICATION_BIRTH}-1******)",
        llm_extractor=None,
    )

    assert CLASSIFICATION_BIRTH not in captured["text"]
    assert "******-*******" in captured["text"]
