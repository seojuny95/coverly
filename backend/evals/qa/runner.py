"""Shared execution primitives for live QA evaluations.

Both the general 상담 suite and the Agent+RAG integration suite exercise the
real ``POST /qa/stream`` route. This module owns that common HTTP/Agent wiring
so the two suites differ only in fixtures and RAG providers.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

from agents import Agent, Runner
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.integrations.openai import ConversationMessage
from app.main import create_app
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import PortfolioSessionSnapshot
from app.modules.qa.context import QaContext
from app.modules.qa.route import get_agent_stream_runner
from evals.qa.judge import RubricVerdict, judge_turn
from evals.qa.rules import CheckResult, ToolCall, TurnOutcome, check_turn

_SESSION_ID = "qa-live-fixture-session"
_UNLIMITED_TURNS = 999

ContextConfigurator = Callable[[QaContext], None]


@dataclass(frozen=True)
class AgentUsage:
    """Model requests and tokens reported by one Agents SDK run."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class FixtureSessions:
    """Stand-in session service backed by fixed evaluation policies."""

    def __init__(
        self,
        policies: tuple[PolicyInput, ...],
        *,
        rag_session_ids: tuple[str, ...] = (),
    ) -> None:
        self._policies = policies
        self._rag_session_ids = rag_session_ids

    def consume_counsel_turn(self, token: str, **_kwargs: object) -> int:
        return _UNLIMITED_TURNS

    def snapshot(self, token: str, **_kwargs: object) -> PortfolioSessionSnapshot:
        return PortfolioSessionSnapshot(
            session_id=token,
            version=1,
            policies=self._policies,
            rag_session_ids=self._rag_session_ids,
        )


@dataclass
class TurnTrace:
    """Agent activity that is not present in the public SSE response."""

    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)
    agent_usage: AgentUsage = field(default_factory=AgentUsage)


class Recorder:
    """Capture tool activity while forwarding the real Agent text stream."""

    def __init__(self, configure_context: ContextConfigurator | None = None) -> None:
        self.current = TurnTrace()
        self._configure_context = configure_context

    def start_turn(self) -> None:
        self.current = TurnTrace()

    async def agent_stream_runner(
        self,
        agent: Agent[QaContext],
        conversation: list[ConversationMessage],
        context: QaContext,
    ) -> AsyncGenerator[str, None]:
        if self._configure_context is not None:
            self._configure_context(context)

        result = Runner.run_streamed(
            agent,
            input=list(conversation),
            context=context,
            max_turns=get_settings().counsel_agent_max_turns,
        )
        try:
            async for event in result.stream_events():
                if event.type == "run_item_stream_event":
                    self._record_run_item(event.item)
                    continue
                if event.type != "raw_response_event":
                    continue
                if event.data.type == "response.output_text.delta":
                    yield event.data.delta
        finally:
            usage = result.context_wrapper.usage
            self.current.agent_usage = AgentUsage(
                requests=usage.requests,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
            )
            result.cancel()

    def _record_run_item(self, item: object) -> None:
        item_type = getattr(item, "type", None)
        if item_type == "tool_call_item":
            raw_item = getattr(item, "raw_item", None)
            name = getattr(raw_item, "name", None)
            arguments = getattr(raw_item, "arguments", None)
            if name:
                self.current.tool_calls.append(ToolCall(name=name, arguments=arguments or "{}"))
            return
        if item_type == "tool_call_output_item":
            self.current.tool_outputs.append(str(getattr(item, "output", "")))


def build_client(
    recorder: Recorder,
    policies: tuple[PolicyInput, ...],
    *,
    rag_session_ids: tuple[str, ...] = (),
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_portfolio_session_service] = lambda: FixtureSessions(
        policies,
        rag_session_ids=rag_session_ids,
    )
    app.dependency_overrides[get_agent_stream_runner] = lambda: recorder.agent_stream_runner
    return TestClient(app)


@dataclass
class TurnResult:
    case_id: str
    intent: str
    turn_index: int
    question: str
    answer: str
    tool_calls: list[ToolCall]
    tool_outputs: list[str]
    elapsed_seconds: float
    check: CheckResult
    execution_error: str | None = None
    judge_verdicts: dict[str, RubricVerdict] = field(default_factory=dict)
    agent_usage: AgentUsage = field(default_factory=AgentUsage)

    @property
    def tool_names(self) -> list[str]:
        return [call.name for call in self.tool_calls]

    @property
    def passed(self) -> bool:
        return self.check.passed and all(verdict.passed for verdict in self.judge_verdicts.values())

    @property
    def failure_lines(self) -> list[str]:
        lines = list(self.check.failures)
        for key, verdict in self.judge_verdicts.items():
            if not verdict.passed:
                lines.append(f"[judge:{key}] {verdict.reason}")
        return lines


def run_case(
    client: TestClient,
    recorder: Recorder,
    case: dict[str, Any],
    *,
    policies: tuple[PolicyInput, ...],
    rubric_descriptions: dict[str, str],
    run_judge: bool,
) -> list[TurnResult]:
    history: list[dict[str, str]] = []
    history_text_parts: list[str] = []
    results: list[TurnResult] = []

    for index, turn in enumerate(case["turns"], start=1):
        question = str(turn["question"])
        recorder.start_turn()

        started = time.perf_counter()
        try:
            response = client.post(
                "/qa/stream",
                json={"question": question, "history": history, "session_id": _SESSION_ID},
            )
            elapsed_seconds = time.perf_counter() - started
            response.raise_for_status()

            events = _parse_events(response.text)
            _raise_for_stream_error(events)
            answer = "".join(event["text"] for event in events if event["type"] == "delta")
        except Exception as error:  # noqa: BLE001 - execution failures are eval results
            elapsed_seconds = time.perf_counter() - started
            results.extend(
                _execution_failure_results(
                    case=case,
                    failed_turn_index=index,
                    elapsed_seconds=elapsed_seconds,
                    error=error,
                )
            )
            return results

        outcome = TurnOutcome(
            answer=answer,
            tool_calls=list(recorder.current.tool_calls),
            tool_outputs=list(recorder.current.tool_outputs),
            policies=list(policies),
        )
        check = check_turn(turn, outcome)
        judge_verdicts = _judge_verdicts(
            turn=turn,
            check=check,
            question=question,
            history_text="\n".join(history_text_parts),
            answer=answer,
            outcome=outcome,
            rubric_descriptions=rubric_descriptions,
            run_judge=run_judge,
        )

        results.append(
            TurnResult(
                case_id=str(case["id"]),
                intent=str(case.get("intent", "")),
                turn_index=index,
                question=question,
                answer=answer,
                tool_calls=list(outcome.tool_calls),
                tool_outputs=list(outcome.tool_outputs),
                elapsed_seconds=elapsed_seconds,
                check=check,
                judge_verdicts=judge_verdicts,
                agent_usage=recorder.current.agent_usage,
            )
        )

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        history_text_parts.append(f"user: {question}")
        history_text_parts.append(f"assistant: {answer}")

    return results


def _judge_verdicts(
    *,
    turn: dict[str, Any],
    check: CheckResult,
    question: str,
    history_text: str,
    answer: str,
    outcome: TurnOutcome,
    rubric_descriptions: dict[str, str],
    run_judge: bool,
) -> dict[str, RubricVerdict]:
    if not run_judge or not check.judge_rubrics:
        return {}
    return judge_turn(
        question=question,
        history_text=history_text,
        answer=answer,
        grounding_context=_grounding_context(outcome),
        reference_facts=list(turn.get("reference_facts") or []),
        rubric_keys=check.judge_rubrics,
        rubric_descriptions=rubric_descriptions,
    )


def _grounding_context(outcome: TurnOutcome) -> str:
    sections: list[str] = []
    for call in outcome.tool_calls:
        sections.append(f"도구 호출: {call.name}({call.arguments})")
    for output in outcome.tool_outputs:
        sections.append(f"도구 결과: {_truncate(output, 4_000)}")
    return "\n".join(sections)


def _execution_failure_results(
    *,
    case: dict[str, Any],
    failed_turn_index: int,
    elapsed_seconds: float,
    error: Exception,
) -> list[TurnResult]:
    error_name = type(error).__name__
    remaining_turns = case["turns"][failed_turn_index - 1 :]
    results: list[TurnResult] = []

    for offset, turn in enumerate(remaining_turns):
        turn_index = failed_turn_index + offset
        failure = (
            f"실행 실패: {error_name}"
            if offset == 0
            else f"이전 턴 실행 실패로 미실행: {error_name}"
        )
        results.append(
            TurnResult(
                case_id=str(case["id"]),
                intent=str(case.get("intent", "")),
                turn_index=turn_index,
                question=str(turn["question"]),
                answer="",
                tool_calls=[],
                tool_outputs=[],
                elapsed_seconds=elapsed_seconds if offset == 0 else 0.0,
                check=CheckResult(failures=[failure]),
                execution_error=error_name,
            )
        )

    return results


def _parse_events(body: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def _raise_for_stream_error(events: list[dict[str, Any]]) -> None:
    if any(event.get("type") == "error" for event in events):
        raise RuntimeError("SSE stream returned an error event")


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[:limit]}…"
