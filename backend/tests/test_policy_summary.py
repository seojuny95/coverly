from app.services.policy.summary import extract_policy_summary


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
        """,
        llm_extractor=None,
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
        "만기일": "2027-01-01",
        "보험료": {
            "금액": 120000,
            "납입주기": "월납",
        },
        "보험분류": "미분류",
        "상품태그": [],
    }


def test_extract_policy_summary_handles_missing_fields_without_guessing() -> None:
    result = extract_policy_summary(
        """
        보험증권
        보험사: 현대해상
        보험기간: 2026-02-03 ~ 2027-02-03
        """,
        llm_extractor=None,
    )

    assert result == {
        "보험사": "현대해상",
        "보험기간": {
            "시작일": "2026-02-03",
            "종료일": "2027-02-03",
        },
        "만기일": "2027-02-03",
        "보험분류": "미분류",
        "상품태그": [],
    }


def test_extract_policy_summary_reads_hyundai_auto_product_from_table_layout() -> None:
    result = extract_policy_summary(
        """
        기본사항
        증권번호 발행일
        보험기간 보험종목
        보험계약자 보험계약자주소
        기명피보험자 피보험자주소
        관계자
        POLICY-TEST-MASKED-003 2026 06 30
        2026-06-27 ~ 2027-06-27 24:00 까지
        테스트고객A(TESTBIRTH-A-*******) 테스트주소
        테스트주소
        테스트고객A(TESTBIRTH-A-*******)
        Hicar 다이렉트개인용
        """,
        llm_extractor=None,
    )

    assert "보험사" not in result
    assert result["상품명"] == "Hicar 다이렉트개인용"


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
        """,
        llm_extractor=None,
    )

    assert result == {
        "상품명": "The좋은종합보험",
        "증권번호": "POLICY-TEST-004",
        "보험료": {
            "금액": 98765,
            "납입주기": "연납",
        },
        "보험분류": "미분류",
        "상품태그": [],
    }


def test_extract_policy_summary_treats_contract_number_as_policy_number() -> None:
    result = extract_policy_summary(
        """
        보험증권
        계약번호: POLICY-TEST-005
        """,
        llm_extractor=None,
    )

    assert result == {
        "증권번호": "POLICY-TEST-005",
        "보험분류": "미분류",
        "상품태그": [],
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
        "홈페이지www.idbins.com",
        llm_extractor=None,
    )

    assert result == {
        "상품명": "무배당 프로미라이프 참좋은운전자상해보험(TM)2404",
        "증권번호": "POLICY-TEST-MASKED-001",
        "계약자": "테스트고객A",
        "피보험자": "테스트고객A",
        "보험기간": {
            "시작일": "2024-07-26",
            "종료일": "2044-07-26",
        },
        "만기일": "2044-07-26",
        "납입기간": "20년납",
        "보험료": {
            "금액": 11670,
            "납입주기": "월납",
        },
        "보험분류": "배상·화재·기타",
        "상품태그": ["운전자"],
    }


def test_extract_policy_summary_fills_missing_display_fields_from_llm_without_overriding() -> None:
    result = extract_policy_summary(
        """
        보험증권
        상품명: 건강보험
        증권번호: POLICY-TEST-001
        피보험자: 가나
        """,
        llm_extractor=lambda _text: {
            "보험사": "삼성화재",
            "상품명": "LLM이 잘못 추출한 상품명",
            "계약자": "가나",
            "보험기간": {
                "시작일": "2026-01-01",
                "종료일": "2027-01-01",
            },
            "보험료": {
                "금액": 120000,
                "납입주기": "월납",
            },
        },
    )

    assert result["보험사"] == "삼성화재"
    assert result["상품명"] == "건강보험"
    assert result["증권번호"] == "POLICY-TEST-001"
    assert result["계약자"] == "가나"
    assert result["피보험자"] == "가나"
    assert result["보험기간"] == {
        "시작일": "2026-01-01",
        "종료일": "2027-01-01",
    }
    assert result["보험료"] == {
        "금액": 120000,
        "납입주기": "월납",
    }
