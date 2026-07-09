from app.services.policy_summary import extract_policy_summary


def test_extract_policy_summary_reads_payment_period_and_maturity_date() -> None:
    result = extract_policy_summary(
        """
        보험증권
        상품명: 건강보험
        보험기간: 2026.01.01 ~ 2046.01.01
        계약사항: 20년만기 / 20년납 / 월납
        보험료: 월 120,000원
        """
    )

    assert result["보험기간"] == {
        "시작일": "2026-01-01",
        "종료일": "2046-01-01",
    }
    assert result["납입기간"] == "20년납"
    assert result["만기일"] == "2046-01-01"
    assert result["보험료"] == {
        "금액": 120000,
        "납입주기": "월납",
    }


def test_extract_policy_summary_keeps_payment_cycle_stable_with_autopay_text() -> None:
    result = extract_policy_summary(
        """
        보험증권
        1회 보험료 79,032원(월납, 카드자동이체)
        계약사항 20년만기 / 20년납 / 월납 / 개인계약 / 신용카드
        보험기간 2020-05-06 ~ 2095-05-06
        """
    )

    assert result["보험료"] == {
        "금액": 79032,
        "납입주기": "월납",
    }
    assert result["납입기간"] == "20년납"
    assert result["만기일"] == "2095-05-06"


def test_extract_policy_summary_does_not_guess_calendar_maturity_from_lifetime_terms() -> None:
    result = extract_policy_summary(
        """
        보험증권
        무배당 평생안심 종신보험
        계약사항 종신 / 20년납 / 월납
        보험료 35,000원
        """
    )

    assert result["납입기간"] == "20년납"
    assert "만기일" not in result


def test_extract_policy_summary_reads_collapsed_payment_period_text() -> None:
    result = extract_policy_summary(
        "기본정보보험종목무배당 프로미라이프 참좋은운전자상해보험(TM)2404"
        "증권번호POLICY-TEST-MASKED-001계약자테스트고객A"
        "(TESTBIRTH-A-1******)보험기간2024년 07월 26일 ~ 2044년 07월 26일"
        "테스트주소 ******계약사항20년만기 / 20년납 / "
        "월납 / 개인계약 / 신용카드만기보험금수익자테스트고객A"
        "보험료11,670원 [보장보험료 11,668원 / 적립보험료 2원]"
    )

    assert result["납입기간"] == "20년납"
    assert result["만기일"] == "2044-07-26"
