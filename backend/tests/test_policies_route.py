import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.policy.pipeline import EmptyTextError, PipelineResult


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
    # Real run_pipeline / parse_document: pdfplumber can't read this body, so it
    # degrades to an empty ParsedDocument and the pipeline raises EmptyTextError.
    client = TestClient(app)

    response = client.post(
        "/policies/parse",
        files={"file": ("broken.pdf", b"%PDF-1.7\nbroken", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDF_TEXT_EXTRACTION_FAILED"
    assert response.json()["error"]["message"] == "PDF에서 텍스트를 추출할 수 없습니다."


def test_parse_returns_pipeline_result_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import policies

    result: PipelineResult = {
        "기본정보": {
            "보험사": "삼성화재",
            "상품명": "건강보험",
            "보험분류": "상해·질병·실손",
            "상품태그": ["질병"],
        },
        "보장목록": [
            {
                "담보명": "암진단비",
                "가입금액": "3,000만원",
                "보장내용": None,
                "해설": "암으로 진단받으면 약속된 금액을 드려요.",
            }
        ],
        "분석상태": "완료",
        "문자수": 42,
    }
    monkeypatch.setattr(policies, "run_pipeline", lambda _data: result)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "accepted", **result}


def test_parse_runs_coverage_extraction_for_auto_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    # The auto-policy skip is gone: every classified policy, including 자동차,
    # now runs through the same pipeline and can return non-empty 보장목록.
    from app.routes import policies

    result: PipelineResult = {
        "기본정보": {"보험분류": "자동차", "상품명": "Hicar 다이렉트개인용"},
        "보장목록": [{"담보명": "대인배상", "가입금액": "무한", "보장내용": None, "해설": None}],
        "분석상태": "완료",
        "문자수": 10,
    }
    monkeypatch.setattr(policies, "run_pipeline", lambda _data: result)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("auto.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["기본정보"]["보험분류"] == "자동차"
    assert payload["보장목록"] == result["보장목록"]
    assert payload["분석상태"] == "완료"


def test_parse_maps_empty_text_error_to_422(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import policies

    def _raise(_data: bytes) -> PipelineResult:
        raise EmptyTextError

    monkeypatch.setattr(policies, "run_pipeline", _raise)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDF_TEXT_EXTRACTION_FAILED"


def test_delete_policy_text_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routes import policies

    deleted: list[str] = []
    monkeypatch.setattr(policies, "delete_policy_session", deleted.append)

    client = TestClient(app)
    response = client.delete("/policies/sessions/session-1")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    assert deleted == ["session-1"]
