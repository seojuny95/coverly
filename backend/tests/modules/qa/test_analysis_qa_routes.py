from functools import partial

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.qa.router import get_portfolio_answer_streamer
from app.modules.qa.router import router as qa_router
from app.modules.qa.service import stream_portfolio_answer


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(qa_router)
    app.dependency_overrides[get_portfolio_answer_streamer] = lambda: partial(
        stream_portfolio_answer,
        agent_runner=None,
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
