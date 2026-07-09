from app.services.policy_summary import extract_policy_summary


def test_extract_policy_summary_reads_core_fields() -> None:
    result = extract_policy_summary(
        """
        보험증권
        보험사: 삼성화재해상보험주식회사
        상품명: 마이헬스파트너
        증권번호: POLICY-TEST-002
        계약자: 가나
        피보험자: 가나
        보험기간: 2026.01.01 ~ 2027.01.01
        보험료: 월 120,000원
        """
    )

    assert result == {
        "보험사": "삼성화재해상보험주식회사",
        "상품명": "마이헬스파트너",
        "증권번호": "POLICY-TEST-002",
        "계약자": "가나",
        "피보험자": "가나",
        "보험기간": {
            "시작일": "2026-01-01",
            "종료일": "2027-01-01",
        },
        "보험료": {
            "금액": 120000,
            "납입주기": "월납",
        },
    }


def test_extract_policy_summary_handles_missing_fields_without_guessing() -> None:
    result = extract_policy_summary(
        """
        보험증권
        보험사: 현대해상
        보험기간: 2026-02-03 ~ 2027-02-03
        """
    )

    assert result == {
        "보험사": "현대해상",
        "보험기간": {
            "시작일": "2026-02-03",
            "종료일": "2027-02-03",
        },
    }


def test_extract_policy_summary_reads_multiline_labels() -> None:
    result = extract_policy_summary(
        """
        보험증권
        상품명
        The좋은종합보험
        증권번호
        POLICY-TEST-004
        보험료
        98,765원 연납
        """
    )

    assert result == {
        "상품명": "The좋은종합보험",
        "증권번호": "POLICY-TEST-004",
        "보험료": {
            "금액": 98765,
            "납입주기": "연납",
        },
    }


def test_extract_policy_summary_treats_contract_number_as_policy_number() -> None:
    result = extract_policy_summary(
        """
        보험증권
        계약번호: POLICY-TEST-005
        """
    )

    assert result == {
        "증권번호": "POLICY-TEST-005",
    }


def test_extract_policy_summary_reads_collapsed_pdf_text() -> None:
    result = extract_policy_summary(
        "기본정보보험종목무배당 프로미라이프 참좋은운전자상해보험(TM)2404"
        "증권번호POLICY-TEST-MASKED-001계약자테스트고객A"
        "(TESTBIRTH-A-1******)보험기간2024년 07월 26일 ~ 2044년 07월 26일"
        "테스트주소 ******계약사항20년만기 / 20년납 / "
        "월납 / 개인계약 / 신용카드만기보험금수익자테스트고객A"
        "보험료11,670원 [보장보험료 11,668원 / 적립보험료 2원]"
        "가입정보피보험자테스트고객A (TESTBIRTH-A-1******)판매플랜간편심사플랜"
        "홈페이지www.idbins.com"
    )

    assert result == {
        "보험사": "DB손해보험",
        "상품명": "무배당 프로미라이프 참좋은운전자상해보험(TM)2404",
        "증권번호": "POLICY-TEST-MASKED-001",
        "계약자": "테스트고객A",
        "피보험자": "테스트고객A",
        "보험기간": {
            "시작일": "2024-07-26",
            "종료일": "2044-07-26",
        },
        "보험료": {
            "금액": 11670,
            "납입주기": "월납",
        },
    }
