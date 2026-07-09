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


def test_parse_rejects_pdf_without_insurance_policy_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routes import policies

    client = TestClient(app)
    monkeypatch.setattr(policies, "extract_pdf_text", lambda _data: "회의록 참석자 안건 결정사항")

    response = client.post(
        "/policies/parse",
        files={"file": ("meeting.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "POLICY_DOCUMENT_NOT_DETECTED"
    assert response.json()["error"]["message"] == "보험증권으로 확인할 수 없습니다."


def test_parse_accepts_pdf_with_insurance_policy_signals(monkeypatch: pytest.MonkeyPatch) -> None:
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

    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "문자수": len(policy_text),
        "문서판정": {
            "보험증권추정": True,
            "점수": 7,
            "근거": [
                "보험증권",
                "증권번호",
                "계약자",
                "피보험자",
                "보험기간",
                "보험료",
                "보험금액",
            ],
        },
        "기본정보": {
            "보험사": "삼성화재",
            "상품명": "건강보험",
            "증권번호": "POLICY-TEST-001",
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
        },
    }
