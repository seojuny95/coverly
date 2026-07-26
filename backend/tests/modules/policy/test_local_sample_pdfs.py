from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.policy.pipeline import PipelineResult
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import PolicyDocumentReservation
from app.modules.portfolio.session.service import (
    PortfolioSessionAccess,
    RegisteredPolicyDocument,
)
from tests.summary_helpers import REQUIRED_DISPLAY_VALUES, SAMPLE_PDF_DIR, flatten_summary

pytestmark = pytest.mark.skipif(
    not SAMPLE_PDF_DIR.exists(),
    reason="local sample PDFs are not available",
)

_STATUS_VALUES = {"완료", "부분"}
_PORTFOLIO_TOKEN = "sample-policy-test-token"


class _Sessions:
    def create(self) -> PortfolioSessionAccess:
        now = datetime.now(UTC)
        return PortfolioSessionAccess(
            token=_PORTFOLIO_TOKEN,
            expires_at=now + timedelta(minutes=15),
        )

    def begin_upload(
        self,
        token: str,
        *,
        document_id: str,
    ) -> PolicyDocumentReservation:
        assert token == _PORTFOLIO_TOKEN
        return PolicyDocumentReservation(
            session_id="sample-policy-test-session",
            document_id=document_id,
            reservation_id=f"reservation-{document_id}",
        )

    def complete_upload(
        self,
        reservation: PolicyDocumentReservation,
        result: PipelineResult,
    ) -> RegisteredPolicyDocument:
        return RegisteredPolicyDocument(id=reservation.document_id)

    def release_upload(self, reservation: PolicyDocumentReservation) -> None:
        pass


def test_local_sample_parse_response_includes_required_display_values() -> None:
    app.dependency_overrides[get_portfolio_session_service] = _Sessions
    try:
        _assert_local_sample_parse_response()
    finally:
        app.dependency_overrides.pop(get_portfolio_session_service, None)


def _assert_local_sample_parse_response() -> None:
    client = TestClient(app)
    session_response = client.post("/portfolio/sessions")
    assert session_response.status_code == 200, "expected portfolio session creation to succeed"
    portfolio_session_token = session_response.json()["portfolioSessionToken"]

    missing_or_wrong_fields: list[str] = []

    for filename, required_values in REQUIRED_DISPLAY_VALUES.items():
        pdf_path = SAMPLE_PDF_DIR / filename
        assert pdf_path.exists(), f"missing local sample PDF: {filename}"

        response = client.post(
            "/policies/parse",
            files={"file": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")},
            data={
                "documentId": str(uuid4()),
                "portfolioSessionToken": portfolio_session_token,
            },
        )

        assert response.status_code == 200, f"{filename}: expected upload acceptance"

        payload = response.json()
        flattened_summary = flatten_summary(payload["기본정보"])
        flattened_required_values = flatten_summary(required_values)

        for field_path, expected_value in flattened_required_values.items():
            actual_value = flattened_summary.get(field_path)
            if actual_value == expected_value:
                continue

            missing_or_wrong_fields.append(
                f"{filename}::{field_path}: expected={expected_value!r}, actual={actual_value!r}"
            )

        assert payload["분석상태"] in _STATUS_VALUES, f"{filename}: unexpected 분석상태"
        assert payload["보장목록"], f"{filename}: expected non-empty coverage list"
        for coverage in payload["보장목록"]:
            assert coverage["담보명"], f"{filename}: coverage row missing 담보명"
            # 부가 rows (auto policy riders) are name-only by design — an empty
            # 가입금액 is their expected shape and no 해설 is generated. Every
            # 담보 row needs an amount plus policy wording or 해설.
            if coverage.get("유형", "담보") == "담보":
                assert coverage["가입금액"], f"{filename}: coverage row missing 가입금액"
                assert coverage["보장내용"] or coverage["해설"], (
                    f"{filename}::{coverage['담보명']} has neither policy wording nor explanation"
                )

    assert not missing_or_wrong_fields, (
        "parse response is missing required display fields\n" + "\n".join(missing_or_wrong_fields)
    )
