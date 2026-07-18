from collections.abc import Iterator
from functools import partial

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import PortfolioSessionSnapshot
from app.modules.qa.agent.contracts import QaAgentCompleted, QaAgentProgress, QaAgentUnavailable
from app.modules.qa.agent.service import stream_answer_with_agent
from app.modules.qa.context import QaContext
from app.modules.qa.router import get_portfolio_answer_streamer
from app.modules.qa.router import router as qa_router
from app.modules.qa.schemas import ConversationMessage, PortfolioQuestionResponse
from app.modules.qa.streaming import QaEndEvent, QaMetaEvent

DOCUMENT_ID = "00000000-0000-0000-0000-000000000001"


class _NoDataAgent:
    def run(self, _context: QaContext) -> PortfolioQuestionResponse:
        return PortfolioQuestionResponse(
            status="no_data",
            answer="업로드된 보험 정보가 없어요.",
            citations=[],
            limitations=[],
        )


class _ProgressAgent:
    def run(self, _context: QaContext) -> PortfolioQuestionResponse:
        raise AssertionError("stream-capable agents must use stream")

    def stream(self, _context: QaContext) -> Iterator[QaAgentProgress | QaAgentCompleted]:
        yield QaAgentProgress(stage="portfolio", text="증권을 확인하고 있어요.")
        yield QaAgentCompleted(
            PortfolioQuestionResponse(
                status="answered",
                answer="확인을 마쳤어요.",
                citations=[],
                limitations=[],
            )
        )


class _FailingAgent:
    def run(self, _context: QaContext) -> PortfolioQuestionResponse:
        raise QaAgentUnavailable("test failure")


def _client() -> TestClient:
    class _Sessions:
        def snapshot(
            self,
            token: str,
            *,
            policy_ids: list[str] | None = None,
        ) -> PortfolioSessionSnapshot:
            return PortfolioSessionSnapshot(
                session_id="portfolio-1",
                version=1,
                policies=(),
                rag_session_ids=(),
            )

    app = FastAPI()
    app.include_router(qa_router)
    app.dependency_overrides[get_portfolio_answer_streamer] = lambda: partial(
        stream_answer_with_agent,
        agent_runner=_NoDataAgent(),
    )
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    return TestClient(app)


def test_qa_stream_route_contract() -> None:
    response = _client().post(
        "/qa/stream",
        json={
            "question": "보험 목록 알려줘",
            "portfolioSessionToken": "portfolio-token",
            "policyIds": [DOCUMENT_ID],
            "demographics": {"age": 35, "gender": "여성", "source": "policy"},
            "history": [{"role": "user", "content": "안녕"}],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type": "meta"' in response.text
    assert '"type": "end"' in response.text
    assert '"status": "no_data"' in response.text


def test_qa_stream_route_validates_blank_question() -> None:
    response = _client().post(
        "/qa/stream",
        json={
            "question": "",
            "portfolioSessionToken": "portfolio-token",
            "policyIds": [DOCUMENT_ID],
        },
    )

    assert response.status_code == 422


def test_qa_stream_loads_policies_and_rag_ids_from_portfolio_session() -> None:
    seen: dict[str, object] = {}
    policy = PolicyInput.model_validate(
        {
            "id": DOCUMENT_ID,
            "기본정보": {"보험사": "보험사A"},
            "보장목록": [],
        }
    )

    class _Sessions:
        def snapshot(
            self,
            token: str,
            *,
            policy_ids: list[str] | None = None,
        ) -> PortfolioSessionSnapshot:
            seen["token"] = token
            seen["policy_ids"] = policy_ids
            return PortfolioSessionSnapshot(
                session_id="portfolio-1",
                version=1,
                policies=(policy,),
                rag_session_ids=("rag-document-1",),
            )

    def _stream(
        question: str,
        policies: list[PolicyInput],
        **kwargs: object,
    ) -> Iterator[QaMetaEvent | QaEndEvent]:
        seen["question"] = question
        seen["policies"] = policies
        seen["rag_session_ids"] = kwargs["policy_rag_session_ids"]
        seen["history"] = kwargs["history"]
        yield QaMetaEvent(type="meta", status="answered", generation="fallback")
        yield QaEndEvent(
            type="end",
            status="answered",
            generation="fallback",
            citations=[],
            limitations=[],
            suggestions=[],
            claim_channels=None,
        )

    app = FastAPI()
    app.include_router(qa_router)
    app.dependency_overrides[get_portfolio_answer_streamer] = lambda: _stream
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()

    response = TestClient(app).post(
        "/qa/stream",
        json={
            "question": "내 보험 알려줘",
            "portfolioSessionToken": "portfolio-token",
            "policyIds": [DOCUMENT_ID],
            "history": [
                {
                    "role": "user",
                    "content": "x" * 1_200 if index == 14 else f"message-{index}",
                }
                for index in range(15)
            ],
        },
    )

    assert response.status_code == 200
    assert seen["token"] == "portfolio-token"
    assert seen["policy_ids"] == [DOCUMENT_ID.replace("-", "")]
    assert seen["policies"] == [policy]
    assert seen["rag_session_ids"] == ("rag-document-1",)
    history = seen["history"]
    assert isinstance(history, list)
    assert history == [
        ConversationMessage(
            role="user",
            content="x" * 1_000 if index == 14 else f"message-{index}",
        )
        for index in range(3, 15)
    ]


def test_agent_service_streams_progress_before_the_answer() -> None:
    events = list(
        stream_answer_with_agent(
            "가입한 보험을 보여줘",
            [],
            agent_runner=_ProgressAgent(),
        )
    )

    assert [event.type for event in events] == ["progress", "meta", "delta", "end"]
    assert events[0].type == "progress"
    assert events[0].stage == "portfolio"


def test_agent_service_exposes_a_grounded_failure_instead_of_using_legacy_logic() -> None:
    events = list(
        stream_answer_with_agent(
            "가입한 보험을 보여줘",
            [],
            agent_runner=_FailingAgent(),
        )
    )

    assert events[0].type == "meta"
    assert events[0].status == "no_data"
    answer = "".join(event.text for event in events if event.type == "delta")
    assert "근거 조회를 완료하지 못했어요" in answer
