from collections.abc import Iterator
from functools import partial

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.qa.agent.contracts import QaAgentCompleted, QaAgentProgress, QaAgentUnavailable
from app.modules.qa.agent.service import stream_answer_with_agent
from app.modules.qa.context import QaContext
from app.modules.qa.router import get_portfolio_answer_streamer
from app.modules.qa.router import router as qa_router
from app.modules.qa.schemas import PortfolioQuestionResponse


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
    app = FastAPI()
    app.include_router(qa_router)
    app.dependency_overrides[get_portfolio_answer_streamer] = lambda: partial(
        stream_answer_with_agent,
        agent_runner=_NoDataAgent(),
    )
    return TestClient(app)


def test_qa_stream_route_contract() -> None:
    response = _client().post(
        "/qa/stream",
        json={
            "question": "보험 목록 알려줘",
            "policies": [],
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
    response = _client().post("/qa/stream", json={"question": "", "policies": []})

    assert response.status_code == 422


def test_agent_service_streams_progress_before_the_answer() -> None:
    events = list(
        stream_answer_with_agent(
            "가입한 보험을 보여줘",
            [],
            agent_runner=_ProgressAgent(),
        )
    )

    assert [event["type"] for event in events] == ["progress", "meta", "delta", "end"]
    assert events[0]["stage"] == "portfolio"


def test_agent_service_exposes_a_grounded_failure_instead_of_using_legacy_logic() -> None:
    events = list(
        stream_answer_with_agent(
            "가입한 보험을 보여줘",
            [],
            agent_runner=_FailingAgent(),
        )
    )

    assert events[0]["status"] == "no_data"
    answer = "".join(str(event["text"]) for event in events if event["type"] == "delta")
    assert "근거 조회를 완료하지 못했어요" in answer
