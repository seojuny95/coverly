"""Route-level tests for /qa/stream, with a stubbed agent runner.

No real OpenAI call: the agent stream runner is overridden with a canned
generator so this stays a fast, deterministic unit test, per this project's
"LLM 경계는 주입 가능한 completer로 설계하고, 유닛 테스트에서는 stub을 주입한다" rule.

There is no slot registry or structured output anymore (see agent.py's
module docstring) -- the stub yields plain natural-language text, and the
route is expected to forward it to the client unmodified.

The safety-boundary tests at the bottom guard what the route owes every
turn before the agent runs: an invalid session is rejected without the
question ever reaching the model, the turn limit bites first, identifiers
are masked, and only the recent history window goes on the wire.
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
from app.modules.portfolio.session.service import (
    CounselTurnLimitReached,
    InvalidPortfolioSessionToken,
)
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
    """Accepts only _SESSION_ID, so tests can exercise the 403 boundary."""

    def __init__(self, policies: tuple[PolicyInput, ...] = ()) -> None:
        self._policies = policies
        self.turns_used = 0
        self.refund_calls = 0

    def consume_counsel_turn(self, token: str, **_kwargs: object) -> int:
        if token != _SESSION_ID:
            raise InvalidPortfolioSessionToken
        self.turns_used += 1
        return 9

    def refund_counsel_turn(self, token: str, **_kwargs: object) -> None:
        if token != _SESSION_ID:
            raise InvalidPortfolioSessionToken
        self.refund_calls += 1
        self.turns_used = max(0, self.turns_used - 1)

    def snapshot(self, token: str, **_kwargs: object) -> PortfolioSessionSnapshot:
        if token != _SESSION_ID:
            raise InvalidPortfolioSessionToken
        return PortfolioSessionSnapshot(
            session_id=token, version=1, policies=self._policies, rag_session_ids=()
        )


class _ExhaustedSessions(_FixtureSessions):
    """A session whose question quota has already run out."""

    def consume_counsel_turn(self, token: str, **_kwargs: object) -> int:
        raise CounselTurnLimitReached


def _stub_runner(
    chunks: list[str],
    seen_conversations: list[list[ConversationMessage]] | None = None,
) -> AgentStreamRunner:
    async def runner(
        agent: Agent[QaContext], conversation: list[ConversationMessage], context: QaContext
    ) -> AsyncIterator[str]:
        if seen_conversations is not None:
            seen_conversations.append(list(conversation))
        for chunk in chunks:
            yield chunk

    return runner


def _failing_runner(
    seen_conversations: list[list[ConversationMessage]] | None = None,
) -> AgentStreamRunner:
    async def runner(
        agent: Agent[QaContext], conversation: list[ConversationMessage], context: QaContext
    ) -> AsyncIterator[str]:
        if seen_conversations is not None:
            seen_conversations.append(list(conversation))
        yield "확인 중이에요."
        raise RuntimeError("agent failed")

    return runner


def _client(
    policies: tuple[PolicyInput, ...],
    chunks: list[str],
    *,
    sessions: _FixtureSessions | None = None,
    seen_conversations: list[list[ConversationMessage]] | None = None,
    runner: AgentStreamRunner | None = None,
) -> TestClient:
    app = create_app()
    session_service = sessions if sessions is not None else _FixtureSessions(policies)
    app.dependency_overrides[get_portfolio_session_service] = lambda: session_service
    app.dependency_overrides[get_agent_stream_runner] = lambda: (
        runner or _stub_runner(chunks, seen_conversations)
    )
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


def test_agent_failure_refunds_the_turn_and_finishes_the_stream() -> None:
    sessions = _FixtureSessions((_policy("암진단비", "2,000만원", "정액"),))
    client = _client(
        (),
        [],
        sessions=sessions,
        runner=_failing_runner(),
    )

    response = client.post(
        "/qa/stream",
        json={"question": "질문", "history": [], "session_id": _SESSION_ID},
    )

    events = _events(response.text)
    assert response.status_code == 200
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "end"
    assert "답을 가져오지 못했어요" in "".join(_delta_texts(events))
    assert sessions.refund_calls == 1
    assert sessions.turns_used == 0


def test_an_invalid_session_is_rejected_before_the_agent_runs() -> None:
    # The session token is an access boundary: an unauthorized request must
    # never put the question on the wire toward the model.
    seen: list[list[ConversationMessage]] = []
    client = _client((), ["네."], seen_conversations=seen)

    response = client.post(
        "/qa/stream",
        json={"question": "암진단비 알려줘", "history": [], "session_id": "bad-session"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVALID_PORTFOLIO_SESSION"
    assert seen == []


def test_a_session_out_of_turns_is_refused_before_the_agent_runs() -> None:
    # The quota must bite before the agent spends a model call.
    seen: list[list[ConversationMessage]] = []
    client = _client((), ["네."], sessions=_ExhaustedSessions(), seen_conversations=seen)

    response = client.post(
        "/qa/stream",
        json={"question": "암진단비 알려줘", "history": [], "session_id": _SESSION_ID},
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "COUNSEL_TURN_LIMIT_REACHED"
    assert seen == []


def test_the_agent_never_receives_identifiers_the_user_typed() -> None:
    seen: list[list[ConversationMessage]] = []
    client = _client((), ["확인했어요."], seen_conversations=seen)

    client.post(
        "/qa/stream",
        json={
            "question": "제 번호는 010-1234-5678이고 주민번호는 900101-1234567이에요",
            "history": [{"role": "user", "content": "메일은 a@b.com 이에요"}],
            "session_id": _SESSION_ID,
        },
    )

    conversation_text = "".join(
        str(message["content"]) for conversation in seen for message in conversation
    )
    assert conversation_text
    assert "010-1234-5678" not in conversation_text
    assert "900101-1234567" not in conversation_text
    assert "a@b.com" not in conversation_text


def test_the_agent_only_sees_the_most_recent_turns() -> None:
    # The client sends the history, so without a window a single request
    # could carry an arbitrarily long conversation into the model call.
    seen: list[list[ConversationMessage]] = []
    client = _client((), ["네."], seen_conversations=seen)

    long_history = [
        {"role": role, "content": f"{role}-{index}"}
        for index in range(1, 9)
        for role in ("user", "assistant")
    ]
    client.post(
        "/qa/stream",
        json={"question": "지금 질문", "history": long_history, "session_id": _SESSION_ID},
    )

    conversation_text = "".join(
        str(message["content"]) for conversation in seen for message in conversation
    )
    assert "user-8" in conversation_text
    assert "user-1" not in conversation_text
