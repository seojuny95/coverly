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

from app.integrations.openai import ConversationMessage
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
_UNLIMITED_TURNS = 999


def load_fixture_policies() -> tuple[PolicyInput, ...]:
    raw = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return tuple(PolicyInput.model_validate(item) for item in raw)


class FixtureSessions:
    """Stand-in portfolio session service backed by the eval fixture."""

    def __init__(self, policies: tuple[PolicyInput, ...]) -> None:
        self._policies = policies

    def consume_counsel_turn(self, token: str, **_kwargs: object) -> int:
        """Evaluation runs are not subject to the per-session question cap."""

        return _UNLIMITED_TURNS

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
        conversation: list[ConversationMessage],
        context: CounselContext,
    ) -> AsyncIterator[str]:
        result = Runner.run_streamed(agent, input=list(conversation), context=context)
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
            for failure in run.failures:
                counts[failure] = counts.get(failure, 0) + 1
        return counts


def collect_reports(results: list[TurnResult]) -> list[TurnReport]:
    reports: dict[tuple[str, int], TurnReport] = {}
    for result in results:
        key = (result.case_id, result.turn_index)
        report = reports.get(key)
        if report is None:
            report = TurnReport(
                case_id=result.case_id,
                turn_index=result.turn_index,
                question=result.question,
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
    parser = argparse.ArgumentParser(description="Run live counsel eval cases")
    parser.add_argument("--case", action="append", help="case id (repeatable)")
    parser.add_argument("--runs", type=int, default=1, help="repeat every case N times")
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
    for run_index in range(1, args.runs + 1):
        for case in cases:
            label = f"▶ {case['id']}" + (f" ({run_index}/{args.runs})" if args.runs > 1 else "")
            print(label, flush=True)
            try:
                results.extend(run_case(client, recorder, case))
            except Exception as error:  # noqa: BLE001 - report, don't abort the suite
                print(f"  ! 실행 실패: {error}", flush=True)

    print_report(collect_reports(results), args.runs)

    if args.json_path:
        payload = [result.__dict__ for result in results]
        Path(args.json_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"JSON: {args.json_path}")


if __name__ == "__main__":
    main()
