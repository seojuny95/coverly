"""Live qa runner: real single agent against fixture policies.

Runs each dataset case as a real multi-turn conversation through the actual
``POST /qa/stream`` route. Only the portfolio session store is replaced --
the fixture policies stand in for an uploaded portfolio. The agent and its
tools run for real; there is no slot registry or rendering step to trace
(see agent.py's module docstring) -- the answer reaching the client is
exactly what the model wrote.

Rule-based checks (rules.py) always run and cost nothing. The LLM judge
(judge.py) is opt-in via --judge, since it's a real API call per turn --
this project's "반복 중에는 비-LLM 테스트만" policy.

Usage (from backend/):
    uv run python -m evals.qa.live
    uv run python -m evals.qa.live --case grounding_disease_name_not_a_coverage
    uv run python -m evals.qa.live --judge
    uv run python -m evals.qa.live --json report.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

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

_HERE = Path(__file__).parent
_BACKEND_ROOT = _HERE.parent.parent
_DATASET_PATH = _HERE / "dataset.json"
_SESSION_ID = "qa-live-fixture-session"
_UNLIMITED_TURNS = 999


def _load_dataset() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_DATASET_PATH.read_text(encoding="utf-8")))


def _load_fixture_policies(relative_path: str) -> tuple[PolicyInput, ...]:
    raw = json.loads((_BACKEND_ROOT / relative_path).read_text(encoding="utf-8"))
    return tuple(PolicyInput.model_validate(item) for item in raw)


class FixtureSessions:
    """Stand-in portfolio session service backed by the eval fixture."""

    def __init__(self, policies: tuple[PolicyInput, ...]) -> None:
        self._policies = policies

    def consume_counsel_turn(self, token: str, **_kwargs: object) -> int:
        return _UNLIMITED_TURNS

    def snapshot(self, token: str, **_kwargs: object) -> PortfolioSessionSnapshot:
        return PortfolioSessionSnapshot(
            session_id=token, version=1, policies=self._policies, rag_session_ids=()
        )


@dataclass
class TurnTrace:
    """What the turn currently being run actually did, beyond the SSE body."""

    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)
    """Stringified return value of every tool call, for rules.py's
    fabricated-amount check -- a real amount that only exists because a tool
    computed it (e.g. a total) still needs to count as grounded."""


class Recorder:
    """Wraps the real agent runner to capture what a client never sees:
    which tools were called, with what arguments, and what they returned.
    """

    def __init__(self) -> None:
        self.current = TurnTrace()

    def start_turn(self) -> None:
        self.current = TurnTrace()

    async def agent_stream_runner(
        self,
        agent: Agent[QaContext],
        conversation: list[ConversationMessage],
        context: QaContext,
    ) -> AsyncIterator[str]:
        result = Runner.run_streamed(
            agent,
            input=list(conversation),
            context=context,
            max_turns=get_settings().counsel_agent_max_turns,
        )
        async for event in result.stream_events():
            if event.type == "run_item_stream_event":
                if event.item.type == "tool_call_item":
                    raw_item = event.item.raw_item
                    name = getattr(raw_item, "name", None)
                    arguments = getattr(raw_item, "arguments", None)
                    if name:
                        self.current.tool_calls.append(
                            ToolCall(name=name, arguments=arguments or "{}")
                        )
                elif event.item.type == "tool_call_output_item":
                    self.current.tool_outputs.append(str(event.item.output))
                continue
            if event.type != "raw_response_event":
                continue
            if event.data.type == "response.output_text.delta":
                yield event.data.delta


def build_client(recorder: Recorder, policies: tuple[PolicyInput, ...]) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_portfolio_session_service] = lambda: FixtureSessions(policies)
    app.dependency_overrides[get_agent_stream_runner] = lambda: recorder.agent_stream_runner
    return TestClient(app)


def _parse_events(body: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


@dataclass
class TurnResult:
    case_id: str
    intent: str
    turn_index: int
    question: str
    answer: str
    tool_names: list[str]
    check: CheckResult
    judge_verdicts: dict[str, RubricVerdict] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.check.passed and all(v.passed for v in self.judge_verdicts.values())

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
        question = turn["question"]
        recorder.start_turn()

        response = client.post(
            "/qa/stream",
            json={"question": question, "history": history, "session_id": _SESSION_ID},
        )
        response.raise_for_status()

        events = _parse_events(response.text)
        answer = "".join(event["text"] for event in events if event["type"] == "delta")

        outcome = TurnOutcome(
            answer=answer,
            tool_calls=list(recorder.current.tool_calls),
            tool_outputs=list(recorder.current.tool_outputs),
            policies=list(policies),
        )
        check = check_turn(turn, outcome)

        judge_verdicts: dict[str, RubricVerdict] = {}
        if run_judge and check.judge_rubrics:
            judge_verdicts = judge_turn(
                question=question,
                history_text="\n".join(history_text_parts),
                answer=answer,
                rubric_keys=check.judge_rubrics,
                rubric_descriptions=rubric_descriptions,
            )

        results.append(
            TurnResult(
                case_id=case["id"],
                intent=case.get("intent", ""),
                turn_index=index,
                question=question,
                answer=answer,
                tool_names=[call.name for call in outcome.tool_calls],
                check=check,
                judge_verdicts=judge_verdicts,
            )
        )

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        history_text_parts.append(f"user: {question}")
        history_text_parts.append(f"assistant: {answer}")

    return results


@dataclass
class TurnReport:
    """One dataset turn across every run, so flakiness is visible."""

    case_id: str
    turn_index: int
    question: str
    runs: list[TurnResult] = field(default_factory=list)

    @property
    def passes(self) -> int:
        return sum(1 for run in self.runs if run.passed)

    @property
    def is_stable_pass(self) -> bool:
        return self.passes == len(self.runs)

    @property
    def is_stable_fail(self) -> bool:
        return self.passes == 0

    def failure_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for run in self.runs:
            for failure in run.failure_lines:
                counts[failure] = counts.get(failure, 0) + 1
        return counts


def collect_reports(results: list[TurnResult]) -> list[TurnReport]:
    reports: dict[tuple[str, int], TurnReport] = {}
    for result in results:
        key = (result.case_id, result.turn_index)
        report = reports.get(key)
        if report is None:
            report = TurnReport(
                case_id=result.case_id, turn_index=result.turn_index, question=result.question
            )
            reports[key] = report
        report.runs.append(result)
    return list(reports.values())


def print_report(reports: list[TurnReport], runs: int) -> None:
    stable_pass = [r for r in reports if r.is_stable_pass]
    stable_fail = [r for r in reports if r.is_stable_fail]
    flaky = [r for r in reports if not r.is_stable_pass and not r.is_stable_fail]

    print(f"\n턴 {len(reports)}개 × {runs}회")
    print(f"  안정 통과 {len(stable_pass)}   불안정 {len(flaky)}   항상 실패 {len(stable_fail)}\n")

    for label, group in (("불안정", flaky), ("항상 실패", stable_fail), ("안정 통과", stable_pass)):
        if not group:
            continue
        print(f"--- {label}")
        for report in sorted(group, key=lambda r: (r.case_id, r.turn_index)):
            print(
                f"  [{report.passes}/{runs}] {report.case_id}#{report.turn_index} {report.question}"
            )
            for failure, count in sorted(report.failure_counts().items()):
                print(f"         {failure}  ({count}회)")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live qa eval cases")
    parser.add_argument("--case", action="append", help="case id (repeatable)")
    parser.add_argument("--runs", type=int, default=1, help="repeat every case N times")
    parser.add_argument("--judge", action="store_true", help="also run the LLM judge rubrics")
    parser.add_argument("--json", dest="json_path", help="write full results as JSON")
    args = parser.parse_args()

    dataset = _load_dataset()
    cases = dataset["cases"]
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case["id"] in wanted]

    policies = _load_fixture_policies(dataset["fixture"])
    rubric_descriptions = dataset.get("judge_rubrics", {})
    recorder = Recorder()

    results: list[TurnResult] = []
    # Entering the client runs the app's lifespan, which is what hands the
    # agents SDK its key. Without it every agent turn dies on a missing
    # credential (see evals/counsel/live.py, which hit this same trap).
    with build_client(recorder, policies) as client:
        for run_index in range(1, args.runs + 1):
            for case in cases:
                suffix = f" ({run_index}/{args.runs})" if args.runs > 1 else ""
                print(f"▶ {case['id']}{suffix}", flush=True)
                try:
                    results.extend(
                        run_case(
                            client,
                            recorder,
                            case,
                            policies=policies,
                            rubric_descriptions=rubric_descriptions,
                            run_judge=args.judge,
                        )
                    )
                except Exception as error:  # noqa: BLE001 - report, don't abort the suite
                    print(f"  ! 실행 실패: {error}", flush=True)

    print_report(collect_reports(results), args.runs)

    if args.json_path:
        payload = [
            {
                "case_id": result.case_id,
                "intent": result.intent,
                "turn_index": result.turn_index,
                "question": result.question,
                "answer": result.answer,
                "tool_names": result.tool_names,
                "passed": result.passed,
                "failures": result.failure_lines,
            }
            for result in results
        ]
        Path(args.json_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"JSON: {args.json_path}")


if __name__ == "__main__":
    main()
