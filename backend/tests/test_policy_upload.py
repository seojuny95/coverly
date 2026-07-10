import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_parse_rejects_non_pdf_upload() -> None:
    client = TestClient(app)

    response = client.post(
        "/policies/parse",
        files={"file": ("note.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_PDF",
            "message": "유효한 PDF 파일이 아닙니다.",
            "request_id": response.headers["x-request-id"],
        },
    }


def test_parse_rejects_pdf_larger_than_limit() -> None:
    client = TestClient(app)
    payload = b"%PDF-" + (b"x" * (10 * 1024 * 1024))

    response = client.post(
        "/policies/parse",
        files={"file": ("large.pdf", payload, "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PDF_TOO_LARGE"
    assert response.json()["error"]["message"] == "파일이 너무 큽니다 (최대 10MB)."
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_parse_rejects_unreadable_pdf_body() -> None:
    client = TestClient(app)

    response = client.post(
        "/policies/parse",
        files={"file": ("broken.pdf", b"%PDF-1.7\nbroken", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDF_TEXT_EXTRACTION_FAILED"
    assert response.json()["error"]["message"] == "PDF에서 텍스트를 추출할 수 없습니다."


def test_parse_accepts_pdf_and_returns_extracted_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import policies

    client = TestClient(app)
    policy_text = """
        보험증권
        보험사: 삼성화재
        상품명: 건강보험
        증권번호: POLICY-TEST-001
        계약자: 가나
        피보험자: 가나
        보험기간: 2026.01.01 ~ 2027.01.01
        보험료: 월 120,000원
        보험금액
        """
    monkeypatch.setattr(
        policies,
        "extract_pdf_text",
        lambda _data: policy_text,
    )
    monkeypatch.setattr(policies, "extract_coverages", lambda _data: ([], "완료"))

    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["문자수"] == len(policy_text)
    assert payload["기본정보"] == {
        "보험사": "삼성화재",
        "상품명": "건강보험",
        "증권번호": "POLICY-TEST-001",
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
        "보험분류": "상해·질병·실손",
        "상품태그": ["질병"],
    }
    assert payload["보장목록"] == []
    assert payload["분석상태"] == "완료"


def test_parse_returns_coverages_with_analysis_status(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import policies

    client = TestClient(app)
    monkeypatch.setattr(policies, "extract_pdf_text", lambda _data: "보험증권 계약자: 가나")
    monkeypatch.setattr(
        policies,
        "extract_coverages",
        lambda _data: (
            [
                {
                    "담보명": "암진단비",
                    "가입금액": "3,000만원",
                    "보장내용": None,
                    "해설": "암으로 진단받으면 약속된 금액을 드려요.",
                }
            ],
            "완료",
        ),
    )

    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["보장목록"] == [
        {
            "담보명": "암진단비",
            "가입금액": "3,000만원",
            "보장내용": None,
            "해설": "암으로 진단받으면 약속된 금액을 드려요.",
        }
    ]
    assert payload["분석상태"] == "완료"


def test_parse_keeps_summary_when_coverage_extraction_is_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routes import policies
    from app.services import classification as classification_module
    from app.services.policy.summary import extract_policy_summary

    # Two LLM seams must be stubbed to keep this test deterministic (the env
    # may carry a real OPENAI_API_KEY):
    # 1. The summary LLM fill would otherwise invent fields (a real call once
    #    hallucinated 상품명 '자동차보험' from this fixture, flipping the
    #    route's auto-policy gate) — disable it via llm_extractor=None.
    # 2. Classification falls through to its LLM fallback tier for this text —
    #    stub it to 미분류 so the auto gate stays closed and the mocked
    #    extract_coverages below actually runs.
    monkeypatch.setattr(
        policies,
        "extract_policy_summary",
        lambda text: extract_policy_summary(text, llm_extractor=None),
    )
    monkeypatch.setattr(
        classification_module,
        "_default_completer",
        lambda: lambda _system, _user: {"보험분류": "미분류"},
    )

    client = TestClient(app)
    monkeypatch.setattr(policies, "extract_pdf_text", lambda _data: "보험사: 삼성화재")
    monkeypatch.setattr(policies, "extract_coverages", lambda _data: ([], "부분"))

    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["기본정보"]["보험사"] == "삼성화재"
    assert payload["보장목록"] == []
    assert payload["분석상태"] == "부분"


def test_parse_skips_coverage_for_auto_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import policies

    client = TestClient(app)
    monkeypatch.setattr(policies, "extract_pdf_text", lambda _data: "자동차 증권 텍스트")
    monkeypatch.setattr(
        policies,
        "extract_policy_summary",
        lambda _text: {"보험분류": "자동차", "상품명": "Hicar 다이렉트개인용"},
    )
    # If the route wrongly ran coverage extraction for an auto policy, this junk
    # would surface in the response; the gate must return an empty 보장목록 instead.
    monkeypatch.setattr(
        policies,
        "extract_coverages",
        lambda _data: (
            [{"담보명": "잘못된담보", "가입금액": "1원", "보장내용": None, "해설": None}],
            "완료",
        ),
    )

    response = client.post(
        "/policies/parse",
        files={"file": ("auto.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["기본정보"]["보험분류"] == "자동차"
    assert payload["보장목록"] == []
    assert payload["분석상태"] == "완료"
