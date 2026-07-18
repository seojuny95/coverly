from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.policy.parsing import (
    PdfPasswordIncorrectError,
    PdfPasswordRequiredError,
)
from app.modules.policy.pipeline import EmptyTextError, PipelineResult
from app.modules.policy.schemas import Coverage as CoverageResponse
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import PolicyDocumentReservation
from app.modules.portfolio.session.service import (
    PortfolioSessionDocumentConflict,
    PortfolioSessionDocumentLimitExceeded,
    RegisteredPolicyDocument,
)
from app.modules.reference_data.loader import ReferenceDataUnavailableError

PORTFOLIO_TOKEN = "test-portfolio-token"
DOCUMENT_ID = "11111111-1111-4111-8111-111111111111"


def test_public_coverage_explanation_basis_is_explicit() -> None:
    base = {
        "담보명": "암진단비",
        "가입금액": "3,000만원",
        "가입금액상태": "confirmed",
        "유형": "담보",
    }

    policy_wording = CoverageResponse.model_validate(
        {**base, "보장내용": "암 진단 확정 시 지급", "해설": None}
    )
    generated_guidance = CoverageResponse.model_validate(
        {**base, "보장내용": None, "해설": "암 진단 시 정액으로 지급하는 담보예요."}
    )
    no_explanation = CoverageResponse.model_validate({**base, "보장내용": None, "해설": None})

    assert policy_wording.설명근거 == "policy_wording"
    assert generated_guidance.설명근거 == "generated_guidance"
    assert no_explanation.설명근거 == "none"


@pytest.fixture(autouse=True)
def _policy_session_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.rag.policy import session_tokens

    class _Settings:
        policy_rag_session_secret = "test-policy-rag-session-secret-32"
        database_url = "postgresql://example/test"

    monkeypatch.setattr(session_tokens, "get_settings", lambda: _Settings())

    class _Sessions:
        def begin_upload(
            self,
            token: str,
            *,
            document_id: str,
        ) -> PolicyDocumentReservation:
            assert token == PORTFOLIO_TOKEN
            assert document_id == "11111111111141118111111111111111"
            return PolicyDocumentReservation(
                session_id="portfolio-session",
                document_id=document_id,
                reservation_id="reservation-1",
            )

        def complete_upload(
            self,
            reservation: PolicyDocumentReservation,
            result: PipelineResult,
        ) -> RegisteredPolicyDocument:
            return RegisteredPolicyDocument(id=reservation.document_id)

        def release_upload(self, reservation: PolicyDocumentReservation) -> None:
            pass

    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    yield
    app.dependency_overrides.pop(get_portfolio_session_service, None)


def test_parse_rejects_non_pdf_upload() -> None:
    client = TestClient(app)

    response = client.post(
        "/policies/parse",
        files={"file": ("note.txt", b"not a pdf", "text/plain")},
        data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_PDF",
            "message": "유효한 PDF 파일이 아닙니다.",
            "request_id": response.headers["x-request-id"],
        },
    }


def test_parse_maps_malformed_multipart_to_common_error() -> None:
    response = TestClient(app).post(
        "/policies/parse",
        content=b"malformed multipart body",
        headers={
            "content-type": "multipart/form-data",
            "x-request-id": "multipart-request",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_MULTIPART_REQUEST",
            "message": "업로드 요청 형식을 확인해주세요.",
            "request_id": "multipart-request",
        }
    }


def test_parse_rejects_pdf_larger_than_limit() -> None:
    client = TestClient(app)
    payload = b"%PDF-" + (b"x" * (10 * 1024 * 1024))

    response = client.post(
        "/policies/parse",
        files={"file": ("large.pdf", payload, "application/pdf")},
        data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
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
        data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDF_TEXT_EXTRACTION_FAILED"
    assert response.json()["error"]["message"] == "PDF에서 텍스트를 추출할 수 없습니다."


def test_parse_returns_pipeline_result_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.upload import router as policies

    result: PipelineResult = {
        "기본정보": {
            "보험사": "삼성화재",
            "상품명": "건강보험",
            "보험분류": "제3보험",
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

    def _run(_data: bytes, *, password: str | None = None) -> PipelineResult:
        return result

    monkeypatch.setattr(policies, "run_pipeline", _run)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
        data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "status": "accepted",
        "documentId": DOCUMENT_ID,
        **result,
        "보장목록": [
            {
                **result["보장목록"][0],
                "가입금액상태": "confirmed",
                "설명근거": "generated_guidance",
                "유형": "담보",
            }
        ],
    }


def test_parse_registers_result_under_portfolio_session_without_exposing_rag_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.upload import router as policies

    result: PipelineResult = {
        "기본정보": {
            "보험사": "보험사A",
            "상품명": "건강보험",
            "보험분류": "제3보험",
            "상품태그": [],
        },
        "보장목록": [],
        "분석상태": "완료",
        "문자수": 42,
        "문서세션ID": "internal-rag-token",
    }
    seen: dict[str, object] = {}

    def _run(_data: bytes, *, password: str | None = None) -> PipelineResult:
        return result

    class _Sessions:
        def begin_upload(
            self,
            token: str,
            *,
            document_id: str,
        ) -> PolicyDocumentReservation:
            seen["token"] = token
            seen["document_id"] = document_id
            return PolicyDocumentReservation(
                session_id="portfolio",
                document_id=document_id,
                reservation_id="reservation-1",
            )

        def complete_upload(
            self,
            reservation: PolicyDocumentReservation,
            pipeline_result: PipelineResult,
        ) -> RegisteredPolicyDocument:
            seen["result"] = pipeline_result
            return RegisteredPolicyDocument(id=reservation.document_id)

        def release_upload(self, reservation: PolicyDocumentReservation) -> None:
            pass

    monkeypatch.setattr(policies, "run_pipeline", _run)
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    try:
        response = TestClient(app).post(
            "/policies/parse",
            files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
            data={"portfolioSessionToken": "portfolio-token", "documentId": DOCUMENT_ID},
        )
    finally:
        app.dependency_overrides.pop(get_portfolio_session_service, None)

    assert response.status_code == 200
    assert response.json()["documentId"] == DOCUMENT_ID
    assert "문서세션ID" not in response.json()
    assert seen == {
        "token": "portfolio-token",
        "result": result,
        "document_id": "11111111111141118111111111111111",
    }


def test_parse_reserves_slot_before_running_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.upload import router as policies

    calls: list[str] = []

    def _run(_data: bytes, *, password: str | None = None) -> PipelineResult:
        calls.append("pipeline")
        return {
            "기본정보": {},
            "보장목록": [],
            "분석상태": "완료",
            "문자수": 1,
        }

    class _Sessions:
        def begin_upload(
            self,
            token: str,
            *,
            document_id: str,
        ) -> PolicyDocumentReservation:
            calls.append("reserve")
            raise PortfolioSessionDocumentLimitExceeded

    monkeypatch.setattr(policies, "run_pipeline", _run)
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    try:
        response = TestClient(app).post(
            "/policies/parse",
            files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
            data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
        )
    finally:
        app.dependency_overrides.pop(get_portfolio_session_service, None)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PORTFOLIO_DOCUMENT_LIMIT_EXCEEDED"
    assert calls == ["reserve"]


def test_parse_rejects_duplicate_document_before_running_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.upload import router as policies

    pipeline_called = False

    def _run(_data: bytes, *, password: str | None = None) -> PipelineResult:
        nonlocal pipeline_called
        pipeline_called = True
        return {
            "기본정보": {},
            "보장목록": [],
            "분석상태": "완료",
            "문자수": 1,
        }

    class _Sessions:
        def begin_upload(
            self,
            token: str,
            *,
            document_id: str,
        ) -> PolicyDocumentReservation:
            raise PortfolioSessionDocumentConflict

    monkeypatch.setattr(policies, "run_pipeline", _run)
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    try:
        response = TestClient(app).post(
            "/policies/parse",
            files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
            data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
        )
    finally:
        app.dependency_overrides.pop(get_portfolio_session_service, None)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "POLICY_UPLOAD_CANCELLED"
    assert not pipeline_called


def test_parse_releases_reservation_when_pipeline_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.upload import router as policies

    released: list[PolicyDocumentReservation] = []
    reservation = PolicyDocumentReservation(
        session_id="portfolio-session",
        document_id="11111111111141118111111111111111",
        reservation_id="reservation-1",
    )

    def _raise(_data: bytes, *, password: str | None = None) -> PipelineResult:
        raise EmptyTextError

    class _Sessions:
        def begin_upload(
            self,
            token: str,
            *,
            document_id: str,
        ) -> PolicyDocumentReservation:
            return reservation

        def release_upload(self, released_reservation: PolicyDocumentReservation) -> None:
            released.append(released_reservation)

    monkeypatch.setattr(policies, "run_pipeline", _raise)
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    try:
        response = TestClient(app).post(
            "/policies/parse",
            files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
            data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
        )
    finally:
        app.dependency_overrides.pop(get_portfolio_session_service, None)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDF_TEXT_EXTRACTION_FAILED"
    assert released == [reservation]


def test_parse_passes_pdf_password_to_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.upload import router as policies

    seen: dict[str, str | None] = {}
    result: PipelineResult = {
        "기본정보": {
            "보험사": "삼성화재",
            "보험분류": "제3보험",
            "상품태그": [],
        },
        "보장목록": [],
        "분석상태": "완료",
        "문자수": 42,
    }

    def _run(_data: bytes, *, password: str | None = None) -> PipelineResult:
        seen["password"] = password
        return result

    monkeypatch.setattr(policies, "run_pipeline", _run)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
        data={
            "password": "900101",
            "portfolioSessionToken": PORTFOLIO_TOKEN,
            "documentId": DOCUMENT_ID,
        },
    )

    assert response.status_code == 200
    assert seen["password"] == "900101"


def test_parse_maps_missing_pdf_password_to_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.upload import router as policies

    def _raise(_data: bytes, *, password: str | None = None) -> PipelineResult:
        raise PdfPasswordRequiredError

    monkeypatch.setattr(policies, "run_pipeline", _raise)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
        data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDF_PASSWORD_REQUIRED"
    assert response.json()["error"]["message"] == "PDF 비밀번호를 입력해주세요."


def test_parse_maps_wrong_pdf_password_to_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.upload import router as policies

    def _raise(_data: bytes, *, password: str | None = None) -> PipelineResult:
        raise PdfPasswordIncorrectError

    monkeypatch.setattr(policies, "run_pipeline", _raise)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
        data={
            "password": "wrong",
            "portfolioSessionToken": PORTFOLIO_TOKEN,
            "documentId": DOCUMENT_ID,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDF_PASSWORD_INCORRECT"
    assert response.json()["error"]["message"] == "PDF 비밀번호가 맞지 않아요. 다시 입력해주세요."


def test_parse_runs_coverage_extraction_for_auto_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    # The auto-policy skip is gone: every classified policy, including 자동차,
    # now runs through the same pipeline and can return non-empty 보장목록.
    from app.modules.upload import router as policies

    result: PipelineResult = {
        "기본정보": {
            "보험분류": "손해보험",
            "상품명": "Hicar 다이렉트개인용",
            "상품태그": ["자동차보험"],
        },
        "보장목록": [{"담보명": "대인배상", "가입금액": "무한", "보장내용": None, "해설": None}],
        "분석상태": "완료",
        "문자수": 10,
    }

    def _run(_data: bytes, *, password: str | None = None) -> PipelineResult:
        return result

    monkeypatch.setattr(policies, "run_pipeline", _run)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("auto.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
        data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["기본정보"]["보험분류"] == "손해보험"
    assert payload["보장목록"] == [
        {
            **result["보장목록"][0],
            "가입금액상태": "confirmed",
            "설명근거": "none",
            "유형": "담보",
        }
    ]
    assert payload["분석상태"] == "완료"


def test_parse_maps_empty_text_error_to_422(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.modules.upload import router as policies

    def _raise(_data: bytes, *, password: str | None = None) -> PipelineResult:
        raise EmptyTextError

    monkeypatch.setattr(policies, "run_pipeline", _raise)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
        data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PDF_TEXT_EXTRACTION_FAILED"


def test_parse_maps_reference_data_failure_to_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.upload import router as policies

    def _raise(_data: bytes, *, password: str | None = None) -> PipelineResult:
        raise ReferenceDataUnavailableError("offline")

    monkeypatch.setattr(policies, "run_pipeline", _raise)

    client = TestClient(app)
    response = client.post(
        "/policies/parse",
        files={"file": ("policy.pdf", b"%PDF-1.7\n%%EOF", "application/pdf")},
        data={"portfolioSessionToken": PORTFOLIO_TOKEN, "documentId": DOCUMENT_ID},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "reference_data_unavailable"
