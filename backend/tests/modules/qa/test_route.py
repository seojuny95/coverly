"""Route-level smoke test for /qa/stream, with a stubbed agent runner.

No real OpenAI call: the agent stream runner is overridden with a canned
generator so this stays a fast, deterministic unit test, per this project's
"LLM 경계는 주입 가능한 completer로 설계하고, 유닛 테스트에서는 stub을 주입한다" rule.

There is no slot registry or structured output anymore (see agent.py's
module docstring) -- the stub yields plain natural-language text, and the
route is expected to forward it to the client unmodified.
"""

import json
from collections.abc import AsyncIterator

from agents import Agent
from fastapi.testclient import TestClient

from app.integrations.openai import ConversationMessage
from app.main import create_app
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import PortfolioSessionSnapshot
from app.modules.qa.agent import AgentStreamRunner
from app.modules.qa.context import QaContext
from app.modules.qa.route import get_agent_stream_runner

_SESSION_ID = "test-session"


def _policy(담보명: str, 가입금액: str, 지급유형: str, 보험사: str = "A화재") -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": "p1",
            "기본정보": {"보험사": 보험사, "상품명": "테스트상품"},
            "보장목록": [{"담보명": 담보명, "가입금액": 가입금액, "지급유형": 지급유형}],
        }
    )


class _FixtureSessions:
    def __init__(self, policies: tuple[PolicyInput, ...]) -> None:
        self._policies = policies

    def consume_counsel_turn(self, token: str, **_kwargs: object) -> int:
        return 9

    def snapshot(self, token: str, **_kwargs: object) -> PortfolioSessionSnapshot:
        return PortfolioSessionSnapshot(
            session_id=token, version=1, policies=self._policies, rag_session_ids=()
        )


def _stub_runner(chunks: list[str]) -> AgentStreamRunner:
    async def runner(
        agent: Agent[QaContext], conversation: list[ConversationMessage], context: QaContext
    ) -> AsyncIterator[str]:
        for chunk in chunks:
            yield chunk

    return runner


def _client(policies: tuple[PolicyInput, ...], chunks: list[str]) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_portfolio_session_service] = lambda: _FixtureSessions(policies)
    app.dependency_overrides[get_agent_stream_runner] = lambda: _stub_runner(chunks)
    return TestClient(app)


def _events(body: str) -> list[dict[str, object]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def _delta_texts(events: list[dict[str, object]]) -> list[str]:
    return [str(event["text"]) for event in events if event["type"] == "delta"]


def test_stream_emits_meta_delta_end_in_order() -> None:
    policies = (_policy("암진단비(유사암제외)", "2,000만원", "정액"),)
    client = _client(policies, ["대장암은 ", "암진단비(유사암제외)로 ", "2,000만원이 나와요."])

    response = client.post(
        "/qa/stream",
        json={"question": "대장암 얼마야?", "history": [], "session_id": _SESSION_ID},
    )

    events = _events(response.text)
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "end"
    assert all(event["type"] == "delta" for event in events[1:-1])
    texts = _delta_texts(events)
    assert "".join(texts) == "대장암은 암진단비(유사암제외)로 2,000만원이 나와요."


def test_meta_carries_real_turns_remaining() -> None:
    policies = (_policy("암진단비(유사암제외)", "2,000만원", "정액"),)
    client = _client(policies, ["확인해 볼게요."])

    response = client.post(
        "/qa/stream",
        json={"question": "질문", "history": [], "session_id": _SESSION_ID},
    )

    meta = _events(response.text)[0]
    assert meta["turns_remaining"] == 9


def test_agent_text_is_forwarded_unmodified() -> None:
    # No slot rendering, no backstop: whatever the agent says (right or
    # wrong) reaches the client as-is. Catching a wrong number is now the
    # eval harness's job (evals/qa/rules.py), not the route's.
    policies = (_policy("암진단비(유사암제외)", "2,000만원", "정액"),)
    client = _client(policies, ["대장암은 암진단비로 3,000만원 나와요."])

    response = client.post(
        "/qa/stream",
        json={"question": "대장암 얼마야?", "history": [], "session_id": _SESSION_ID},
    )

    events = _events(response.text)
    texts = _delta_texts(events)
    assert "".join(texts) == "대장암은 암진단비로 3,000만원 나와요."


def test_empty_deltas_are_not_forwarded() -> None:
    policies = (_policy("암진단비(유사암제외)", "2,000만원", "정액"),)
    client = _client(policies, ["안녕", "", "하세요"])

    response = client.post(
        "/qa/stream",
        json={"question": "질문", "history": [], "session_id": _SESSION_ID},
    )

    events = _events(response.text)
    assert _delta_texts(events) == ["안녕", "하세요"]
