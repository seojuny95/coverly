import pytest

from app.services.policy import classification as classification_module
from app.services.policy.summary import service as summary_module
from app.services.policy.summary.service import (
    _coerce_policy_summary,
    _LlmPolicySummaryExtraction,
    extract_local_policy_summary,
    extract_policy_summary,
    get_insurer_candidates,
)

ADULT_BIRTH = "95" + "0524"
OLDER_HOLDER_BIRTH = "80" + "0101"
SECONDARY_ADULT_BIRTH = "TESTBIRTH-F"


@pytest.fixture(autouse=True)
def _stub_classification_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make classification tier 2 (LLM fallback) deterministic in tests.

    Several fixtures below use product names with no official 보험종목 term
    (e.g. "마이헬스파트너"), so `classify_policy` falls through to the LLM
    fallback. Without stubbing it, these tests would make real OpenAI API
    calls whenever OPENAI_API_KEY is configured, making them slow and
    non-deterministic. Stubbing to 미분류 matches every expectation below;
    cases that hit a deterministic term (e.g. 운전자상해보험) never reach the
    LLM fallback in the first place, so this stub is a no-op for them.
    """

    def stub_completer(_system: str, _user: str) -> dict[str, object]:
        return {"보험분류": "미분류"}

    monkeypatch.setattr(classification_module, "_default_completer", lambda: stub_completer)


def test_llm_filled_vehicle_info_merged_when_plate_grounded() -> None:
    result = extract_policy_summary(
        """
        자동차보험증권
        차량번호 TEST-PLATE-001 차명 아이오닉5
        보험기간: 2026.01.01 ~ 2027.01.01
        """,
        llm_extractor=lambda _t: {
            "차량정보": {"차량명": "아이오닉5", "차량번호": "TEST-PLATE-001", "연식": "2024"}
        },
    )
    assert result["차량정보"]["차량번호"] == "TEST-PLATE-001"


def test_llm_filled_vehicle_info_dropped_when_plate_absent() -> None:
    # cite-or-refuse: 차량번호가 원문에 없으면 차량정보 전체를 버린다.
    result = extract_policy_summary(
        "자동차보험증권\n보험기간: 2026.01.01 ~ 2027.01.01",
        llm_extractor=lambda _t: {
            "차량정보": {"차량명": "아이오닉5", "차량번호": "TEST-PLATE-999", "연식": "2024"}
        },
    )
    assert "차량정보" not in result


def test_llm_vehicle_info_without_plate_is_kept() -> None:
    # 차량명/연식만 있으면(번호 미기재 증권) grounding 대상이 없어 수용.
    result = extract_policy_summary(
        "자동차보험증권\n차명 아이오닉5\n보험기간: 2026.01.01 ~ 2027.01.01",
        llm_extractor=lambda _t: {"차량정보": {"차량명": "아이오닉5"}},
    )
    assert result["차량정보"] == {"차량명": "아이오닉5"}


def test_no_insurer_specific_identifiers_in_module() -> None:
    # 보험사·상품 전용 로직 금지: 소스에 특정 보험사 이름이 남아 있으면 실패.
    import inspect

    src = inspect.getsource(summary_module)
    for forbidden in ("현대해상", "hyundai", "Hyundai", "HYUNDAI"):
        assert forbidden not in src, f"insurer-specific token leaked: {forbidden}"


def test_mock_document_extracts_all_known_fields_exactly() -> None:
    # Mock 문서: 넣은 내용을 알고 있으므로 정확한 추출값을 단언한다(추출 정확성 1순위).
    result = extract_local_policy_summary(
        """
        상품명: 무배당 건강보험
        보험계약자 가나
        증권번호 POLICY-TEST-006
        피보험자 다라
        보험기간 2026.01.01 ~ 2046.01.01
        계약사항: 20년만기 / 20년납 / 월납
        보험료 120,000원 월납
        """
    )
    assert result.get("상품명") == "무배당 건강보험"
    assert result.get("계약자") == "가나"
    assert result.get("피보험자") == "다라"
    assert result.get("증권번호") == "POLICY-TEST-006"
    assert result["보험기간"] == {"시작일": "2026-01-01", "종료일": "2046-01-01"}
    assert result.get("만기일") == "2046-01-01"
    assert result.get("납입기간") == "20년납"
    assert result.get("보험료") == {"금액": 120000, "납입주기": "월납"}


def test_summary_merges_classification() -> None:
    result = extract_policy_summary(
        "상품명: 실손의료보험\n보험기간: 2026.01.01 ~ 2027.01.01",
        llm_extractor=lambda _text: None,
    )
    assert "보험분류" in result
    assert "상품태그" in result


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
    masked_identifier = f"{ADULT_BIRTH}-1******"

    result = extract_policy_summary(
        "기본정보보험종목무배당 프로미라이프 참좋은운전자상해보험(TM)2404"
        "증권번호POLICY-TEST-MASKED-001계약자테스트고객A"
        f"({masked_identifier})보험기간2024년 07월 26일 ~ 2044년 07월 26일"
        "테스트주소 ******계약사항20년만기 / 20년납 / "
        "월납 / 개인계약 / 신용카드만기보험금수익자테스트고객A"
        "보험료11,670원 [보장보험료 11,668원 / 적립보험료 2원]"
        f"가입정보피보험자테스트고객A ({masked_identifier})판매플랜간편심사플랜"
        "홈페이지www.idbins.com",
        llm_extractor=None,
    )

    demographics = result.pop("피보험자정보")
    assert demographics["성별"] == "남성"
    assert demographics["생애단계"] == "성인"
    assert 0 <= demographics["나이"] <= 120

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
        삼성화재에서 발행한 증권입니다.
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


def test_extract_policy_summary_reads_payment_period_and_maturity_date() -> None:
    result = extract_policy_summary(
        """
        보험증권
        상품명: 건강보험
        보험기간: 2026.01.01 ~ 2046.01.01
        계약사항: 20년만기 / 20년납 / 월납
        보험료: 월 120,000원
        """,
        llm_extractor=None,
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


def test_extract_local_policy_summary_reads_premium_from_doubled_bold_glyphs() -> None:
    # pdfplumber renders some bold table labels/amounts with every character
    # doubled back-to-back (a rendering artifact, e.g. "납입보험료" ->
    # "납납입입보보험험료료"); this mirrors a real NH농협보험증권 fragment.
    result = extract_local_policy_summary(
        "계계약약자자주주소소 (자택) 테스트주소\n"
        "납납입입보보험험료료 42,615원 납납입입주주기기 월납\n"
        "보보장장보보험험료료 42,615원 적적립립보보험험료료 해당 없음"
    )

    assert result["보험료"] == {"금액": 42615, "납입주기": "월납"}


def test_extract_local_policy_summary_truncates_product_name_at_glued_policy_number() -> None:
    # Some layouts squeeze multiple fields onto one text line, e.g.
    # "보험종목 <상품명> 증권번호 <번호>" with no newline between them; mirrors a
    # real DB운전자보험증권 fragment.
    masked_identifier = f"{ADULT_BIRTH}-1******"

    result = extract_local_policy_summary(
        "보험종목 무배당 프로미라이프 참좋은운전자상해보험(TM)2404 "
        "증권번호 POLICY-TEST-MASKED-001\n"
        f"테스트고객A ({masked_identifier}) 보험기간 2024년 07월 26일 ~ 2044년 07월 26일\n"
    )

    assert result["상품명"] == "무배당 프로미라이프 참좋은운전자상해보험(TM)2404"


def test_extract_policy_summary_keeps_payment_cycle_stable_with_autopay_text() -> None:
    result = extract_policy_summary(
        """
        보험증권
        1회 보험료 79,032원(월납, 카드자동이체)
        계약사항 20년만기 / 20년납 / 월납 / 개인계약 / 신용카드
        보험기간 2020-05-06 ~ 2095-05-06
        """,
        llm_extractor=None,
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
        """,
        llm_extractor=None,
    )

    assert result["납입기간"] == "20년납"
    assert "만기일" not in result


def test_extract_policy_summary_reads_collapsed_payment_period_text() -> None:
    masked_identifier = f"{ADULT_BIRTH}-1******"

    result = extract_policy_summary(
        "기본정보보험종목무배당 프로미라이프 참좋은운전자상해보험(TM)2404"
        "증권번호POLICY-TEST-MASKED-001계약자테스트고객A"
        f"({masked_identifier})보험기간2024년 07월 26일 ~ 2044년 07월 26일"
        "테스트주소 ******계약사항20년만기 / 20년납 / "
        "월납 / 개인계약 / 신용카드만기보험금수익자테스트고객A"
        "보험료11,670원 [보장보험료 11,668원 / 적립보험료 2원]",
        llm_extractor=None,
    )

    assert result["납입기간"] == "20년납"
    assert result["만기일"] == "2044-07-26"


def test_extract_policy_summary_reads_labeled_table_layout_without_insurer_overrides() -> None:
    # General label-based extraction (no insurer-specific layout logic):
    # product name is inferred from the "(무)"/"무배당" prefix heuristic.
    result = extract_policy_summary(
        """
        상품명
        무배당 다이렉트 운전자보험
        증권번호
        POLICY-TEST-MASKED-003
        계약자
        테스트고객A
        보험기간
        2026-06-27 ~ 2027-06-27
        """,
        llm_extractor=None,
    )

    assert result["상품명"] == "무배당 다이렉트 운전자보험"
    assert result["증권번호"] == "POLICY-TEST-MASKED-003"
    assert result["계약자"] == "테스트고객A"
    assert result["보험기간"] == {
        "시작일": "2026-06-27",
        "종료일": "2027-06-27",
    }


def test_two_column_table_layout_defers_to_llm_fill() -> None:
    # POLICY-TEST-003 / 다이렉트개인용자동차보험 appear here only in this unlabeled
    # footer line, so the LLM-filled values below stay grounded even though the
    # two-column table above defeats local extraction for them.
    holder_identifier = f"{OLDER_HOLDER_BIRTH}-1******"
    insured_identifier = f"{SECONDARY_ADULT_BIRTH}-1******"
    text = f"""
    보험증권 발행일
    보험계약자 보험계약자주소
    증권번호
    발행일
    가나({holder_identifier}) 테스트주소
    기명피보험자 피보험자주소
    다라({insured_identifier}) 테스트주소
    안내: 다이렉트개인용자동차보험 POLICY-TEST-003
    """
    local = extract_local_policy_summary(text)
    assert "계약자" not in local or local["계약자"] not in {"보험계약자주소"}
    assert "피보험자" not in local or local["피보험자"] not in {"피보험자주소"}
    assert local.get("증권번호") != "발행일"
    assert local.get("상품명") != "보험"

    filled = extract_policy_summary(
        text,
        llm_extractor=lambda _t: {
            "증권번호": "POLICY-TEST-003",
            "계약자": "가나",
            "피보험자": "다라",
            "상품명": "다이렉트개인용자동차보험",
        },
    )
    assert filled["계약자"] == "가나"
    assert filled["피보험자"] == "다라"
    assert filled["증권번호"] == "POLICY-TEST-003"


def test_llm_filled_insurer_absent_from_text_is_not_set() -> None:
    # Cite-or-refuse: the enum only constrains the LLM to a catalog insurer, it
    # does not guarantee that insurer is the one named in this document. A value
    # that never appears in the source text must be dropped, not surfaced.
    result = extract_policy_summary(
        """
        보험증권
        상품명: 건강보험
        증권번호: POLICY-TEST-001
        피보험자: 가나
        """,
        llm_extractor=lambda _text: {"보험사": "AXA손해보험"},
    )

    assert "보험사" not in result


def test_llm_filled_insurer_present_in_text_is_set() -> None:
    result = extract_policy_summary(
        """
        보험증권
        AXA손해보험에서 발행한 증권입니다.
        상품명: 건강보험
        증권번호: POLICY-TEST-001
        피보험자: 가나
        """,
        llm_extractor=lambda _text: {"보험사": "AXA손해보험"},
    )

    assert result["보험사"] == "AXA손해보험"


def test_llm_filled_insurer_grounded_by_brand_token_alone() -> None:
    # Documents rarely print the catalog's full legal name ("DB손해보험") — they
    # carry the brand ("DB", "디비손보"). Grounding the insurer on its brand
    # token (legal name minus the generic industry suffix) keeps cite-or-refuse
    # while accepting the document's own naming.
    result = extract_policy_summary(
        """
        보험증권
        DB 다이렉트 고객센터 안내
        상품명: 건강보험
        증권번호: POLICY-TEST-001
        피보험자: 가나
        """,
        llm_extractor=lambda _text: {"보험사": "DB손해보험"},
    )

    assert result["보험사"] == "DB손해보험"


def test_llm_filled_insurer_with_multi_token_brand_requires_every_token() -> None:
    # "NH농협손해보험" -> brand tokens "NH" + "농협"; both must appear, in any
    # position — the document may print them apart ("NH", "농협금융지주").
    result = extract_policy_summary(
        """
        보험증권
        NH 콜센터 / 농협금융지주 계열
        상품명: 건강보험
        증권번호: POLICY-TEST-001
        피보험자: 가나
        """,
        llm_extractor=lambda _text: {"보험사": "NH농협손해보험"},
    )

    assert result["보험사"] == "NH농협손해보험"


def test_llm_filled_insurer_brand_absent_is_still_dropped() -> None:
    # Brand-token grounding must not become a free pass: an insurer whose brand
    # never appears anywhere in the text stays out (the AXA hallucination case).
    result = extract_policy_summary(
        """
        보험증권
        상품명: 건강보험
        증권번호: POLICY-TEST-001
        피보험자: 가나
        보험기간: 2026.01.01 ~ 2027.01.01
        """,
        llm_extractor=lambda _text: {"보험사": "현대해상화재보험"},
    )

    assert "보험사" not in result


def test_llm_insurer_field_is_filtered_to_catalog() -> None:
    candidates = get_insurer_candidates()

    assert {"DB손해보험", "NH농협손해보험", "현대해상화재보험", "흥국화재"}.issubset(
        set(candidates)
    )

    summary = _coerce_policy_summary({"보험사": "후보밖보험"}, candidates)

    assert "보험사" not in summary


def test_llm_summary_model_rejects_extra_fields() -> None:
    schema = _LlmPolicySummaryExtraction.model_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "보험사",
        "상품명",
        "증권번호",
        "계약자",
        "피보험자",
        "보험기간",
        "만기일",
        "납입기간",
        "보험료",
        "차량정보",
    }


def test_llm_summary_coercion_treats_literal_null_as_missing() -> None:
    summary = _coerce_policy_summary(
        {
            "보험사": "null",
            "차량정보": {"차량명": "null", "차량번호": "없음", "연식": "N/A"},
        },
        ("테스트손해보험",),
    )

    assert summary == {}
