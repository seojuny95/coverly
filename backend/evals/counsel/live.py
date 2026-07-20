"""Live counsel runner: real planner LLM + real agent against fixture policies.

Runs each dataset case as a real multi-turn conversation through the actual
``POST /counsel/stream`` route. Only the portfolio session store is replaced —
the fixture policies stand in for an uploaded portfolio so no DB session or
real 증권 is needed. Planner, fact modules, agent, and tools all run for real.

Usage (from backend/):
    uv run python -m evals.counsel.live
    uv run python -m evals.counsel.live --case multiturn_pronoun_chain
    uv run python -m evals.counsel.live --json report.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents import Agent, Runner
from fastapi.testclient import TestClient

from app.integrations.openai.client import structured_completer
from app.main import create_app
from app.modules.counsel.context import CounselContext
from app.modules.counsel.planner import CounselPlan
from app.modules.counsel.router import get_agent_stream_runner, get_plan_completer
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import PortfolioSessionSnapshot

_HERE = Path(__file__).parent
_FIXTURE_PATH = _HERE / "fixture_policies.json"
_DATASET_PATH = _HERE / "dataset.json"
_SESSION_ID = "live-fixture-session"


def load_fixture_policies() -> tuple[PolicyInput, ...]:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return tuple(PolicyInput.model_validate(item) for item in raw)


class FixtureSessions:
    """Stand-in portfolio session service backed by the eval fixture."""

    def __init__(self, policies: tuple[PolicyInput, ...]) -> None:
        self._policies = policies

    def snapshot(self, token: str, **_kwargs: object) -> PortfolioSessionSnapshot:
        return PortfolioSessionSnapshot(
            session_id=token,
            version=1,
            policies=self._policies,
            rag_session_ids=(),
        )


@dataclass
class TurnTrace:
    """What one live turn actually did, for the report."""

    plan: dict[str, Any] | None = None
    tools: list[str] = field(default_factory=list)


class Recorder:
    """Collects the plan and tool calls of the turn currently being run."""

    def __init__(self) -> None:
        self.current = TurnTrace()

    def start_turn(self) -> None:
        self.current = TurnTrace()

    def plan_completer(self, real_complete: Any) -> Any:
        def complete(system: str, user: str) -> Any:
            raw = real_complete(system, user)
            self.current.plan = raw if isinstance(raw, dict) else None
            return raw

        return complete

    async def agent_stream_runner(
        self,
        agent: Agent[CounselContext],
        input_text: str,
        context: CounselContext,
    ) -> AsyncIterator[str]:
        result = Runner.run_streamed(agent, input=input_text, context=context)
        async for event in result.stream_events():
            if event.type == "run_item_stream_event":
                if event.item.type == "tool_call_item":
                    name = getattr(event.item.raw_item, "name", None)
                    if name:
                        self.current.tools.append(name)
                continue
            if event.type != "raw_response_event":
                continue
            if event.data.type == "response.output_text.delta":
                yield event.data.delta


def build_client(recorder: Recorder) -> TestClient:
    app = create_app()
    policies = load_fixture_policies()
    app.dependency_overrides[get_portfolio_session_service] = lambda: FixtureSessions(policies)
    app.dependency_overrides[get_plan_completer] = lambda: recorder.plan_completer(
        structured_completer(CounselPlan)
    )
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
    rewritten: str
    in_scope: bool
    excluded_note: str | None
    answer: str
    plan: dict[str, Any] | None
    tools: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return not self.failures


def _check(turn: dict[str, Any], meta: dict[str, Any], answer: str) -> list[str]:
    failures: list[str] = []

    expected_scope = turn.get("expected_in_scope")
    if expected_scope is not None and meta["in_scope"] is not expected_scope:
        failures.append(f"in_scope={meta['in_scope']} (기대 {expected_scope})")

    include_any = turn.get("must_include_any") or []
    if include_any and not any(token in answer for token in include_any):
        failures.append(f"must_include_any 미충족: {include_any}")

    for token in turn.get("must_include_all") or []:
        if token not in answer:
            failures.append(f"must_include_all 누락: {token}")

    for token in turn.get("must_not_include") or []:
        if token in answer:
            failures.append(f"must_not_include 위반: {token}")

    rewrite = meta.get("rewritten_question") or ""
    rewrite_any = turn.get("expect_rewrite_contains_any") or []
    if rewrite_any and not any(token in rewrite for token in rewrite_any):
        failures.append(f"재작성에 {rewrite_any} 없음: {rewrite!r}")

    for token in turn.get("expect_rewrite_not_contains") or []:
        if token in rewrite:
            failures.append(f"재작성 오염: {token!r} in {rewrite!r}")

    if turn.get("expect_excluded_note") and not meta.get("excluded_note"):
        failures.append("excluded_note 없음")

    return failures


def run_case(client: TestClient, recorder: Recorder, case: dict[str, Any]) -> list[TurnResult]:
    history: list[dict[str, str]] = []
    results: list[TurnResult] = []

    for index, turn in enumerate(case["turns"], start=1):
        question = turn["question"]
        recorder.start_turn()

        response = client.post(
            "/counsel/stream",
            json={"question": question, "history": history, "session_id": _SESSION_ID},
        )
        response.raise_for_status()

        events = _parse_events(response.text)
        meta = next(event for event in events if event["type"] == "meta")
        answer = "".join(event["text"] for event in events if event["type"] == "delta")

        results.append(
            TurnResult(
                case_id=case["id"],
                intent=case.get("intent", ""),
                turn_index=index,
                question=question,
                rewritten=meta.get("rewritten_question", ""),
                in_scope=bool(meta["in_scope"]),
                excluded_note=meta.get("excluded_note"),
                answer=answer,
                plan=recorder.current.plan,
                tools=list(recorder.current.tools),
                failures=_check(turn, meta, answer),
            )
        )

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live counsel eval cases")
    parser.add_argument("--case", action="append", help="case id (repeatable)")
    parser.add_argument("--json", dest="json_path", help="write full results as JSON")
    args = parser.parse_args()

    dataset = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case["id"] in wanted]

    recorder = Recorder()
    client = build_client(recorder)

    results: list[TurnResult] = []
    for case in cases:
        print(f"▶ {case['id']}", flush=True)
        try:
            results.extend(run_case(client, recorder, case))
        except Exception as error:  # noqa: BLE001 - report, don't abort the suite
            print(f"  ! 실행 실패: {error}", flush=True)

    passed = sum(1 for result in results if result.passed)
    print(f"\n{passed}/{len(results)} turns passed\n")
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        print(f"[{mark}] {result.case_id}#{result.turn_index} {result.question}")
        if result.failures:
            for failure in result.failures:
                print(f"       - {failure}")

    if args.json_path:
        payload = [result.__dict__ for result in results]
        Path(args.json_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON: {args.json_path}")


if __name__ == "__main__":
    main()
