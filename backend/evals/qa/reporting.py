"""Report aggregation and serialization for live QA evaluations."""

from __future__ import annotations

from dataclasses import dataclass, field

from evals.qa.runner import TurnResult

_MAX_TOOL_OUTPUT_CHARS = 4_000


@dataclass
class TurnReport:
    """One dataset turn across every run, making model variance visible."""

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
                case_id=result.case_id,
                turn_index=result.turn_index,
                question=result.question,
            )
            reports[key] = report
        report.runs.append(result)
    return list(reports.values())


def print_report(reports: list[TurnReport], runs: int) -> None:
    stable_pass = [report for report in reports if report.is_stable_pass]
    stable_fail = [report for report in reports if report.is_stable_fail]
    flaky = [
        report for report in reports if not report.is_stable_pass and not report.is_stable_fail
    ]

    print(f"\n턴 {len(reports)}개 × {runs}회")
    print(f"  안정 통과 {len(stable_pass)}   불안정 {len(flaky)}   항상 실패 {len(stable_fail)}\n")

    groups = (
        ("불안정", flaky),
        ("항상 실패", stable_fail),
        ("안정 통과", stable_pass),
    )
    for label, group in groups:
        if not group:
            continue
        print(f"--- {label}")
        for report in sorted(group, key=lambda item: (item.case_id, item.turn_index)):
            print(
                f"  [{report.passes}/{runs}] {report.case_id}#{report.turn_index} {report.question}"
            )
            for failure, count in sorted(report.failure_counts().items()):
                print(f"         {failure}  ({count}회)")
        print()


def result_payload(result: TurnResult) -> dict[str, object]:
    return {
        "case_id": result.case_id,
        "intent": result.intent,
        "turn_index": result.turn_index,
        "question": result.question,
        "answer": result.answer,
        "tool_names": result.tool_names,
        "tool_calls": [
            {"name": call.name, "arguments": call.arguments} for call in result.tool_calls
        ],
        "tool_outputs": [
            _truncate(output, _MAX_TOOL_OUTPUT_CHARS) for output in result.tool_outputs
        ],
        "elapsed_seconds": round(result.elapsed_seconds, 3),
        "agent_usage": {
            "requests": result.agent_usage.requests,
            "input_tokens": result.agent_usage.input_tokens,
            "output_tokens": result.agent_usage.output_tokens,
            "total_tokens": result.agent_usage.total_tokens,
        },
        "passed": result.passed,
        "execution_error": result.execution_error,
        "failures": result.failure_lines,
    }


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[:limit]}…"
