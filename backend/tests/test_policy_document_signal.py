from app.services.policy_document import classify_policy_document


def test_policy_document_signal_accepts_common_policy_fields() -> None:
    result = classify_policy_document(
        """
        보험증권
        증권번호: P-2026-0001
        계약자: 가나
        피보험자: 가나
        보험기간: 2026.01.01 ~ 2027.01.01
        보험료: 월 120,000원
        보험금액: 1,000만원
        """
    )

    assert result.is_likely_policy is True
    assert result.score >= 10
    assert "보험증권" in result.matched_terms
    assert "증권번호" in result.matched_terms
    assert "보험기간값" in result.matched_terms


def test_policy_document_signal_accepts_policy_without_title_text() -> None:
    result = classify_policy_document(
        """
        보험종목 무배당 운전자보험
        계약번호 POLICY-TEST-MASKED-001
        계약자 테스트고객A
        피보험자 테스트고객A
        보험기간 2024년 07월 26일 ~ 2044년 07월 26일
        1회 보험료 11,670원(월납)
        보장내용 자동차부상치료비
        """
    )

    assert result.is_likely_policy is True
    assert result.score >= 10
    assert "계약번호" in result.matched_terms
    assert "보험료값" in result.matched_terms


def test_policy_document_signal_rejects_generic_documents() -> None:
    result = classify_policy_document("회의록 참석자 안건 결정사항 다음 회의 일정")

    assert result.is_likely_policy is False
    assert result.score < 7
    assert result.matched_terms == []


def test_policy_document_signal_rejects_policy_related_brochure_without_policy_structure() -> None:
    result = classify_policy_document(
        """
        보험약관 주요 안내문
        상품설명서
        계약자와 피보험자의 권리 안내
        보험료 할인 조건
        청약서 작성 예시
        """
    )

    assert result.is_likely_policy is False
    assert result.score < 7
    assert "계약자값" not in result.matched_terms
    assert "증권번호값" not in result.matched_terms


def test_policy_document_signal_accepts_collapsed_pdf_text() -> None:
    result = classify_policy_document(
        "기본정보보험종목무배당 프로미라이프 참좋은운전자상해보험(TM)2404"
        "증권번호POLICY-TEST-MASKED-001계약자테스트고객A"
        "(TESTBIRTH-A-1******)보험기간2024년 07월 26일 ~ 2044년 07월 26일"
        "테스트주소 ******계약사항20년만기 / 20년납 / "
        "월납 / 개인계약 / 신용카드만기보험금수익자테스트고객A"
        "보험료11,670원 [보장보험료 11,668원 / 적립보험료 2원]"
        "가입정보피보험자테스트고객A (TESTBIRTH-A-1******)판매플랜간편심사플랜"
        "홈페이지www.idbins.com"
    )

    assert result.is_likely_policy is True
    assert result.score >= 10
    assert "증권번호값" in result.matched_terms
    assert "보험기간값" in result.matched_terms
