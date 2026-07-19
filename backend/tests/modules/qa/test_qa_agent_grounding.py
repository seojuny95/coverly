from app.modules.consultation.contracts import ConsultationEvidence
from app.modules.qa.agent.grounding import (
    NUMERIC_CLAIM,
    numeric_claims_grounded_in_sources,
)


def _evidence(fact: str) -> ConsultationEvidence:
    return ConsultationEvidence(id="e", fact=fact)


def test_numbers_from_two_sources_are_grounded_together() -> None:
    # 3,000만원은 첫 근거에, 2,000만원은 둘째 근거에 있다.
    answer = "암진단비는 두 증권 합쳐 3,000만원과 2,000만원이 확인돼요."
    ok = numeric_claims_grounded_in_sources(
        answer,
        authoritative_answers=["암진단비 30,000,000원 확인", "암진단비 20,000,000원 확인"],
        evidence=(),
    )
    assert ok is True


def test_number_absent_from_all_sources_is_not_grounded() -> None:
    answer = "합계는 9,999만원이에요."
    ok = numeric_claims_grounded_in_sources(
        answer,
        authoritative_answers=["암진단비 30,000,000원 확인"],
        evidence=(_evidence("암진단비 20,000,000원 확인"),),
    )
    assert ok is False


_SRC = ["보험사A 암진단비 30,000,000원 확인", "보험사B 암진단비 20,000,000원 확인"]


def test_compound_won_fabrication_is_rejected() -> None:
    # 근거는 3천만+2천만인데 지어낸 1억2천만원은 통과하면 안 된다 (억 누락 버그)
    assert not numeric_claims_grounded_in_sources("두 증권 합쳐 총 1억2천만원이에요.", _SRC, ())


def test_compound_won_matches_when_source_has_it() -> None:
    assert numeric_claims_grounded_in_sources(
        "총 1억2천만원이에요.", ["합계 120,000,000원 확인"], ()
    )
    assert numeric_claims_grounded_in_sources("총 1억2천만원이에요.", ["합계 1억 2천만원 확인"], ())


def test_hangul_numeral_money_is_not_silently_passed() -> None:
    # 한글 숫자 금액은 검증 불가 → fail-closed
    assert not numeric_claims_grounded_in_sources("암진단비는 삼천만원이에요.", _SRC, ())


def test_spaced_hangul_money_is_not_silently_passed() -> None:
    # 표준 띄어쓰기(삼천만 원)도 한글 숫자 금액이므로 검증 불가 → fail-closed
    assert not numeric_claims_grounded_in_sources("암진단비는 삼천만 원이에요.", _SRC, ())
    assert not numeric_claims_grounded_in_sources("암진단비는 오천만 원이에요.", _SRC, ())
    assert not numeric_claims_grounded_in_sources("암진단비는 일억 원이에요.", _SRC, ())


def test_spaced_hangul_money_is_detected_by_numeric_claim() -> None:
    # 가드로 쓰이는 NUMERIC_CLAIM이 띄어쓴 한글 금액을 놓치면 안 된다
    assert NUMERIC_CLAIM.search("삼천만 원") is not None


def test_positional_compound_won_matches_source_value() -> None:
    # 2천5백만 = 2500만 = 25,000,000 (자리값 파싱). 정당한 답이 통과해야 한다.
    assert numeric_claims_grounded_in_sources(
        "보장은 2천5백만원이에요.", ["보장 25,000,000원 확인"], ()
    )
    assert numeric_claims_grounded_in_sources(
        "보장은 1억2천5백만원이에요.", ["보장 125,000,000원 확인"], ()
    )


def test_positional_compound_won_fabrication_is_rejected() -> None:
    # 자리값을 올바로 계산해도 근거에 없는 값은 여전히 fail-closed
    assert not numeric_claims_grounded_in_sources("보장은 2천5백만원이에요.", _SRC, ())


def test_bare_magnitude_amount_is_checked() -> None:
    # 원 없는 단위 금액도 새어나가면 안 된다
    assert not numeric_claims_grounded_in_sources("합계 5000만이에요.", _SRC, ())


def test_non_money_counters_are_unaffected() -> None:
    # 카운터/비율은 기존대로 (과잉 발동 금지) — 소스에 있는 값은 통과
    assert numeric_claims_grounded_in_sources(
        "보장은 2건, 대기기간 90일이에요.",
        ["가입 2건 확인", "대기기간 90일"],
        (),
    )
