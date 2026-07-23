import asyncio
from threading import Event, Lock

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.policy.pipeline import PipelineResult
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import PolicyDocumentReservation
from app.modules.portfolio.session.service import RegisteredPolicyDocument
from app.modules.upload.parsing_capacity import (
    PdfParsingCapacity,
    get_pdf_parsing_capacity,
)
from app.modules.upload.router import get_policy_pipeline


class _Sessions:
    def begin_upload(
        self,
        token: str,
        *,
        document_id: str,
    ) -> PolicyDocumentReservation:
        assert token == "portfolio-token"
        return PolicyDocumentReservation(
            session_id="portfolio-session",
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


def test_five_http_uploads_complete_with_bounded_server_concurrency() -> None:
    async def run_scenario() -> None:
        release = Event()
        two_started = Event()
        state_lock = Lock()
        active = 0
        max_active = 0

        def pipeline(_data: bytes, *, password: str | None = None) -> PipelineResult:
            nonlocal active, max_active
            with state_lock:
                active += 1
                max_active = max(max_active, active)
                if active == 2:
                    two_started.set()
            release.wait(timeout=2)
            with state_lock:
                active -= 1
            return {
                "기본정보": {
                    "보험사": "테스트보험",
                    "상품명": "테스트상품",
                    "보험분류": "제3보험",
                    "상품태그": ["질병"],
                },
                "보장목록": [],
                "분석상태": "완료",
                "policy_terms_status": "unavailable",
                "문자수": 1,
            }

        capacity = PdfParsingCapacity(
            concurrency_limit=2,
            queue_limit=3,
            queue_timeout_seconds=1,
        )
        app.dependency_overrides[get_policy_pipeline] = lambda: pipeline
        app.dependency_overrides[get_portfolio_session_service] = _Sessions
        app.dependency_overrides[get_pdf_parsing_capacity] = lambda: capacity

        transport = ASGITransport(app=app)
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                uploads = [
                    asyncio.create_task(
                        client.post(
                            "/policies/parse",
                            files={
                                "file": (
                                    f"policy-{index}.pdf",
                                    b"%PDF-1.7\n%%EOF",
                                    "application/pdf",
                                )
                            },
                            data={
                                "portfolioSessionToken": "portfolio-token",
                                "documentId": f"00000000-0000-4000-8000-{index:012d}",
                            },
                        )
                    )
                    for index in range(5)
                ]
                assert await asyncio.to_thread(two_started.wait, 1)
                assert max_active == 2

                release.set()
                responses = await asyncio.gather(*uploads)
        finally:
            release.set()
            app.dependency_overrides.pop(get_policy_pipeline, None)
            app.dependency_overrides.pop(get_portfolio_session_service, None)
            app.dependency_overrides.pop(get_pdf_parsing_capacity, None)

        assert [response.status_code for response in responses] == [200] * 5
        assert max_active == 2

    asyncio.run(run_scenario())
