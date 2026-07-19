from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.counsel.router import get_agent_runner, get_check_completer
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


def _fake_agent_runner(answer: str) -> Any:
    async def run(_agent: object, _input_text: str, _context: object) -> object:
        return SimpleNamespace(final_output=answer)

    return run


def test_stream_endpoint_returns_the_agent_answer_when_in_scope() -> None:
    app = create_app()
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    app.dependency_overrides[get_check_completer] = lambda: _in_scope_completer("암진단비 알려줘")
    app.dependency_overrides[get_agent_runner] = lambda: _fake_agent_runner("암진단비가 확인돼요.")
    client = TestClient(app)

    response = client.post(
        "/counsel/stream",
        json={"question": "암진단비 알려줘", "history": [], "session_id": "valid-session"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "암진단비가 확인돼요.",
        "in_scope": True,
        "rewritten_question": "암진단비 알려줘",
    }


def test_stream_endpoint_refuses_when_out_of_scope() -> None:
    app = create_app()
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    app.dependency_overrides[get_check_completer] = _out_of_scope_completer
    client = TestClient(app)

    response = client.post(
        "/counsel/stream",
        json={"question": "오늘 날씨 알려줘", "history": [], "session_id": "valid-session"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["in_scope"] is False
    assert "answer" in body


def test_stream_endpoint_rejects_an_invalid_session() -> None:
    # asyncio.gather starts both tasks concurrently, so the check-completer must
    # still be overridden even though this test only cares about the session
    # failure — otherwise the real OpenAI client would run alongside it.
    app = create_app()
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()
    app.dependency_overrides[get_check_completer] = lambda: _in_scope_completer("암진단비 알려줘")
    client = TestClient(app)

    response = client.post(
        "/counsel/stream",
        json={"question": "암진단비 알려줘", "history": [], "session_id": "bad-session"},
    )

    assert response.status_code == 403
