"""Trace one counsel conversation stage by stage.

The live runner answers "did this turn come out right". This answers "which
stage made it wrong": what the planner was handed, what it planned, which facts
came back, what the escalation gate decided, and what the agent finally read.

Every stage is captured by wrapping the functions the route already calls, so
the runtime code stays untouched and the trace reflects the real pipeline.

Usage (from backend/):
    uv run python -m evals.counsel.inspect --case history_after_out_of_scope
    uv run python -m evals.counsel.inspect --ask "겹치는 보장 있어?" --ask "오늘 날씨 어때?"
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import app.modules.counsel.answer.stream as stream_stage
import app.modules.counsel.router as router_stage
from evals.counsel.live import Recorder, build_client

_DATASET_PATH = Path(__file__).parent / "dataset.json"
_SESSION_ID = "inspect-fixture-session"
_WIDTH = 100


@dataclass
class TurnTrace:
    """What each stage of one turn received and produced."""

    stages: list[tuple[str, str]] = field(default_factory=list)

    def record(self, stage: str, detail: str) -> None:
        self.stages.append((stage, detail))


class PipelineTracer:
    """Wrap the pipeline's stage functions and record what passes through."""

    def __init__(self) -> None:
        self.current = TurnTrace()

    def start_turn(self) -> None:
        self.current = TurnTrace()

    @contextmanager
    def patched(self) -> Iterator[None]:
        """Swap each stage function for one that records, and restore on exit."""

        wrapped: list[tuple[Any, str, Any]] = []
        for module, name, stage, describe in _TRACED_STAGES:
            original = getattr(module, name)
            wrapped.append((module, name, original))
            setattr(module, name, self._wrap(stage, original, describe))
        try:
            yield
        finally:
            for module, name, original in wrapped:
                setattr(module, name, original)

    def _wrap(
        self,
        stage: str,
        original: Callable[..., Any],
        describe: Callable[[Any], str],
    ) -> Callable[..., Any]:
        def traced(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            self.current.record(stage, describe(result))
            return result

        return traced

    def plan_completer(self, real_complete: Any) -> Any:
        """Record the planner's own input and output, which no wrapper can see."""

        def complete(system: str, user: str) -> Any:
            self.current.record("2. planner 입력", f"{len(system):,}자 지시 + {len(user):,}자 대화")
            raw = real_complete(system, user)
            self.current.record("3. plan", _describe_plan(raw))
            return raw

        return complete


def _describe_history(history: Any) -> str:
    turns = list(history)
    if not turns:
        return "없음"
    chars = sum(len(turn.content) for turn in turns)
    longest = max(turns, key=lambda turn: len(turn.content))
    return (
        f"{len(turns)}개 메시지, 총 {chars:,}자 "
        f"(가장 긴 것 {len(longest.content):,}자 · {longest.role})"
    )


def _describe_plan(raw: Any) -> str:
    if not isinstance(raw, dict):
        return f"구조화 실패: {raw!r}"
    tasks = ", ".join(task.get("kind", "?") for task in raw.get("tasks") or []) or "없음"
    return "\n".join(
        [
            f"question_without_history: {raw.get('question_without_history')!r}",
            f"needs_history: {raw.get('needs_history')}",
            f"rewritten_question:       {raw.get('rewritten_question')!r}",
            f"in_scope: {raw.get('in_scope')} · mode: {raw.get('response_mode')} · tasks: {tasks}",
        ]
    )


def _describe_execution(execution: Any) -> str:
    lines = []
    for result in execution.results:
        matched, unmatched = _count_matches(result)
        names = ", ".join(result.task.coverage_names) or "-"
        lines.append(
            f"{result.task.kind} (요청 담보: {names}): 매칭 {matched} · 미매칭 {unmatched}"
        )
    return "\n".join(lines) or "실행한 작업 없음"


def _count_matches(result: Any) -> tuple[int, int]:
    matched = 0
    unmatched = 0
    for source in (result.coverage_lookup, result.coverage_total, result.claim_channels):
        if source is None:
            continue
        matched += len(getattr(source, "matches", None) or getattr(source, "included", []))
        unmatched += len(source.unmatched)
    return matched, unmatched


def _describe_text(text: Any) -> str:
    if text is None:
        return "없음"
    return f"{len(text):,}자 | {_preview(text)}"


def _describe_route(route: Any) -> str:
    return (
        f"사실 표시: {route.shows_facts} · agent 실행: {route.run_agent} · "
        f"확인 필요 문구: {route.needs_hedge}"
    )


def _describe_agent_input(messages: Any) -> str:
    items = list(messages)
    total = sum(len(str(item["content"])) for item in items)
    lines = [f"{len(items)}개 메시지, 총 {total:,}자"]
    for item in items:
        content = str(item["content"])
        lines.append(f"  [{item['role']}] {len(content):,}자 | {_preview(content)}")
    return "\n".join(lines)


# Stage number, the module attribute to wrap, and how to summarize its result.
# Stages 2 and 3 are the planner call itself, which is recorded by the completer.
_TRACED_STAGES: tuple[tuple[Any, str, str, Any], ...] = (
    (router_stage, "recent_turns", "1. history", _describe_history),
    (stream_stage, "execute_fact_tasks", "4. facts", _describe_execution),
    (stream_stage, "compose_fact_answer", "5. 화면에 쓸 사실", _describe_text),
    (stream_stage, "compose_agent_facts", "6. agent에 줄 사실", _describe_text),
    (stream_stage, "route_answer", "7. 에스컬레이션", _describe_route),
    (stream_stage, "build_agent_input", "8. agent 입력", _describe_agent_input),
)


def _preview(text: str) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= 70 else flat[:69] + "…"


def _questions(args: argparse.Namespace) -> list[str]:
    if args.ask:
        return list(args.ask)

    dataset = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    for case in dataset["cases"]:
        if case["id"] == args.case:
            return [turn["question"] for turn in case["turns"]]
    raise SystemExit(f"case not found: {args.case}")


def _print_turn(index: int, question: str, trace: TurnTrace, answer: str) -> None:
    print("=" * _WIDTH)
    print(f"턴 {index} — {question}")
    print("=" * _WIDTH)
    for stage, detail in trace.stages:
        print(f"\n[{stage}]")
        for line in detail.splitlines():
            print(f"  {line}")
    print("\n[9. 최종 답변]")
    print(f"  {len(answer):,}자 | {_preview(answer)}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace a counsel conversation stage by stage")
    parser.add_argument("--case", help="dataset case id to replay")
    parser.add_argument("--ask", action="append", help="ask this question (repeatable)")
    args = parser.parse_args()
    if not args.case and not args.ask:
        raise SystemExit("pass --case or --ask")

    questions = _questions(args)
    tracer = PipelineTracer()
    recorder = Recorder()
    recorder.plan_completer = tracer.plan_completer  # type: ignore[method-assign]

    history: list[dict[str, str]] = []
    with tracer.patched(), build_client(recorder) as client:
        for index, question in enumerate(questions, start=1):
            tracer.start_turn()
            response = client.post(
                "/counsel/stream",
                json={"question": question, "history": history, "session_id": _SESSION_ID},
            )
            response.raise_for_status()

            events = [
                json.loads(line.removeprefix("data: "))
                for line in response.text.splitlines()
                if line.startswith("data: ")
            ]
            answer = "".join(event["text"] for event in events if event["type"] == "delta")

            _print_turn(index, question, tracer.current, answer)
            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
