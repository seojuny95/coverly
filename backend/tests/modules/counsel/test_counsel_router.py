import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.counsel.router import get_agent_stream_runner, get_plan_completer
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import PortfolioSessionSnapshot
from app.modules.portfolio.session.service import InvalidPortfolioSessionToken


class _Sessions:
    def snapshot(self, token: str, **_kwargs: object) -> PortfolioSessionSnapshot:
        if token != "valid-session":
            raise InvalidPortfolioSessionToken
        return PortfolioSessionSnapshot(
            session_id=token,
            version=1,
            policies=(
                PolicyInput.model_validate(
                    {"id": "p1", "기본정보": {"보험사": "테스트보험사"}, "보장목록": []}
                ),
            ),
            rag_session_ids=(),
        )


def _in_scope_completer(rewritten: str) -> object:
    return lambda _system, _user: {
        "rewritten_question": rewritten,
        "in_scope": True,
        "reason": "보험 질문",
    }


def _out_of_scope_completer() -> object:
    return lambda _system, _user: {
        "rewritten_question": "오늘 날씨 알려줘",
        "in_scope": False,
        "reason": "보험과 무관",
    }


def _fake_agent_stream_runner(*chunks: str) -> Any:
    async def run(_agent: object, _input_text: str, _context: object) -> AsyncIterator[str]:
        for chunk in chunks:
            yield chunk

    return run


def _parse_sse_events(body: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def test_stream_endpoint_streams_meta_then_deltas_then_end_when_in_scope() -> None:
    app = create_app()
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    app.dependency_overrides[get_plan_completer] = lambda: _in_scope_completer("암진단비 알려줘")
    app.dependency_overrides[get_agent_stream_runner] = lambda: _fake_agent_stream_runner(
        "암진단비가 ", "확인돼요."
    )
    client = TestClient(app)

    response = client.post(
        "/counsel/stream",
        json={"question": "암진단비 알려줘", "history": [], "session_id": "valid-session"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse_events(response.text)
    assert events == [
        {
            "type": "meta",
            "in_scope": True,
            "rewritten_question": "암진단비 알려줘",
            "excluded_note": None,
        },
        {"type": "delta", "text": "암진단비가 "},
        {"type": "delta", "text": "확인돼요."},
        {"type": "end"},
    ]


def test_stream_endpoint_streams_a_refusal_when_out_of_scope() -> None:
    app = create_app()
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    app.dependency_overrides[get_plan_completer] = _out_of_scope_completer
    client = TestClient(app)

    response = client.post(
        "/counsel/stream",
        json={"question": "오늘 날씨 알려줘", "history": [], "session_id": "valid-session"},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events[0]["type"] == "meta"
    assert events[0]["in_scope"] is False
    assert events[-1] == {"type": "end"}
    assert any(event["type"] == "delta" for event in events)


def test_stream_endpoint_rejects_an_invalid_session() -> None:
    # asyncio.gather starts both tasks concurrently, so the check-completer must
    # still be overridden even though this test only cares about the session
    # failure — otherwise the real OpenAI client would run alongside it.
    app = create_app()
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    app.dependency_overrides[get_plan_completer] = lambda: _in_scope_completer("암진단비 알려줘")
    client = TestClient(app)

    response = client.post(
        "/counsel/stream",
        json={"question": "암진단비 알려줘", "history": [], "session_id": "bad-session"},
    )

    assert response.status_code == 403
