"""Contract and live end-to-end evaluation for portfolio QA."""

from __future__ import annotations

import json
from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Literal, cast

from app.modules.evidence.catalog import citation_from_evidence
from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent.contracts import AgentCounselorDraft, QaAgentDependencies, QaAgentRunner
from app.modules.qa.agent.runtime import build_qa_agent_runner
from app.modules.qa.agent.service import stream_answer_with_agent
from app.modules.qa.agent.validation import validated_agent_response
from app.modules.qa.context import QaContext
from app.modules.qa.response_support import out_of_scope_response
from app.modules.qa.schemas import ConversationMessage, PortfolioQuestionResponse
from app.modules.qa.streaming import QaDeltaEvent, QaEndEvent
from app.modules.qa.tools.evidence import portfolio_snapshot_evidence
from app.modules.qa.tools.web_search import WebSearchResult

EVAL_FIXTURE = Path(__file__).resolve().parent / "dataset.json"
POLICY_FIXTURE = Path(__file__).resolve().parent / "fixture_policies.json"
EvalRoute = Literal["agent", "agent_no_tool", "input_guardrail"]

_UNIVERSAL_FORBIDDEN = (
    "안심하세요",
    "반드시 가입",
    "가입하세요",
    "무조건 지급",
)


@dataclass(frozen=True)
class QaEvalCase:
    id: str
    question: str
    profile: str
    expected_route: EvalRoute
    expected_status: str
    must_include_groups: tuple[tuple[str, ...], ...]
    required_evidence_terms: tuple[str, ...]
    must_not_include: tuple[str, ...]
    history: tuple[ConversationMessage, ...]
    live: bool
    require_citations: bool


@dataclass(frozen=True)
class QaEvalResult:
    case_id: str
    profile: str
    passed: bool
    route_passed: bool
    contract_passed: bool
    content_evaluated: bool
    content_passed: bool
    evidence_passed: bool
    status: str
    generation: str
    agent_calls: int
    citation_count: int
    no_tool_passed: bool
    elapsed_ms: float
    answer: str
    failures: tuple[str, ...]


@dataclass(frozen=True)
class QaEvalReport:
    mode: str
    passed: int
    total: int
    contract_passed: int
    content_evaluated: int
    content_passed: int
    results: tuple[QaEvalResult, ...]
    model: str | None = None

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


class _ProbeAgent:
    def __init__(
        self,
        *,
        expected_route: EvalRoute,
        expected_status: str,
        delegate: QaAgentRunner | None = None,
    ) -> None:
        self.expected_route = expected_route
        self.expected_status = expected_status
        self.delegate = delegate
        self.calls = 0
        self.last_context: QaContext | None = None

    def run(self, context: QaContext) -> PortfolioQuestionResponse:
        self.calls += 1
        self.last_context = context
        if self.delegate is not None:
            return self.delegate.run(context)

        if self.expected_route == "input_guardrail":
            return out_of_scope_response(context)

        if self.expected_route == "agent_no_tool":
            dependencies = QaAgentDependencies(
                context=context,
                complete=None,
                official_answer=None,
                web_search=lambda *_args, **_kwargs: WebSearchResult(status="unavailable"),
            )
            return validated_agent_response(
                context,
                AgentCounselorDraft(
                    answer_mode="general_guidance",
                    answer=(
                        "저는 올려주신 보험증권을 기준으로 가입 보험, 담보, 가입금액, "
                        "겹치는 보장, 청구 방법을 함께 확인해드릴 수 있어요. "
                        "개인정보와 증권 내용은 답변 근거 확인에 필요한 범위에서만 다룹니다. "
                        "지급 조건은 약관 근거가 필요해서 확인 없이 단정하지 않습니다."
                    ),
                ),
                dependencies,
            )

        if self.expected_status == "no_data":
            return PortfolioQuestionResponse(
                status="no_data",
                answer="질문에 필요한 근거를 확인하지 못했습니다.",
                citations=[],
                limitations=["근거 조회 결과가 없는 계약을 확인했습니다."],
            )

        evidence = portfolio_snapshot_evidence(context)
        citations = [citation_from_evidence(item) for item in evidence[:3]]
        return PortfolioQuestionResponse(
            status="answered",
            answer="Agent가 요청한 도구에서 업로드 증권 근거를 확인할 수 있습니다.",
            citations=citations,
            limitations=[],
        )


def load_cases(path: Path = EVAL_FIXTURE) -> tuple[QaEvalCase, ...]:
    payload = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
    rows = cast(list[dict[str, object]], payload["cases"])
    return tuple(_case_from_json(row) for row in rows)


def evaluate(
    cases: tuple[QaEvalCase, ...] | None = None,
    *,
    live: bool = False,
    model: str | None = None,
) -> QaEvalReport:
    active_cases = cases if cases is not None else load_cases()
    delegate = build_qa_agent_runner(model=model) if live else None
    results = tuple(_evaluate_case(case, delegate=delegate, live=live) for case in active_cases)
    evaluated = tuple(result for result in results if result.content_evaluated)
    return QaEvalReport(
        mode="live" if live else "baseline",
        passed=sum(result.passed for result in results),
        total=len(results),
        contract_passed=sum(result.contract_passed for result in results),
        content_evaluated=len(evaluated),
        content_passed=sum(result.content_passed for result in evaluated),
        results=results,
        model=model,
    )


def render_report(report: QaEvalReport, *, show_passing: bool = False) -> str:
    elapsed = [result.elapsed_ms for result in report.results]
    average_ms = sum(elapsed) / len(elapsed) if elapsed else 0.0
    median_ms = median(elapsed) if elapsed else 0.0
    lines = [
        (
            f"mode={report.mode} passed={report.passed}/{report.total} "
            f"pass_rate={report.pass_rate:.3f} "
            f"contracts={report.contract_passed}/{report.total} "
            f"content={report.content_passed}/{report.content_evaluated} "
            f"model={report.model or 'default'} "
            f"avg_elapsed_ms={average_ms:.1f} median_elapsed_ms={median_ms:.1f}"
        )
    ]
    for result in report.results:
        if result.passed and not show_passing:
            continue
        state = "PASS" if result.passed else "FAIL"
        lines.append(
            f"{state} {result.case_id} route_calls={result.agent_calls} "
            f"status={result.status} generation={result.generation} "
            f"no_tool={result.no_tool_passed} "
            f"elapsed_ms={result.elapsed_ms:.1f}"
        )
        for failure in result.failures:
            lines.append(f"  - {failure}")
        if result.answer:
            lines.append(f"  answer: {result.answer}")
    return "\n".join(lines)


def _evaluate_case(
    case: QaEvalCase,
    *,
    delegate: QaAgentRunner | None,
    live: bool,
) -> QaEvalResult:
    probe = _ProbeAgent(
        expected_route=case.expected_route,
        expected_status=case.expected_status,
        delegate=delegate,
    )
    started = perf_counter()
    try:
        events = list(
            stream_answer_with_agent(
                case.question,
                fixture_policies(),
                history=list(case.history),
                agent_runner=probe,
            )
        )
        elapsed_ms = (perf_counter() - started) * 1000
        answer = "".join(event.text for event in events if isinstance(event, QaDeltaEvent))
        end = events[-1]
        if not isinstance(end, QaEndEvent):
            raise ValueError("QA stream did not finish with an end event")
        status = end.status
        generation = end.generation
        citations = end.citations
        rendered_output = _render_eval_output(answer, end)
    except Exception as exc:
        elapsed_ms = (perf_counter() - started) * 1000
        return QaEvalResult(
            case_id=case.id,
            profile=case.profile,
            passed=False,
            route_passed=False,
            contract_passed=False,
            content_evaluated=live or case.expected_route != "agent",
            content_passed=False,
            evidence_passed=False,
            status="error",
            generation="error",
            agent_calls=probe.calls,
            citation_count=0,
            no_tool_passed=False,
            elapsed_ms=elapsed_ms,
            answer="",
            failures=(f"{type(exc).__name__}: {exc}",),
        )

    expected_calls = 1
    route_passed = probe.calls == expected_calls
    content_evaluated = live or case.expected_route in {"agent_no_tool", "input_guardrail"}
    include_passed = all(
        any(term in rendered_output for term in group) for group in case.must_include_groups
    )
    forbidden = (*_UNIVERSAL_FORBIDDEN, *case.must_not_include)
    forbidden_passed = all(term not in answer for term in forbidden)
    status_passed = status == case.expected_status
    citations_passed = not case.require_citations or bool(citations)
    generation_passed = (
        not (live and case.expected_route == "agent" and case.expected_status == "answered")
        or generation == "llm"
    )
    limitations = end.limitations
    no_tool_passed = case.expected_route != "agent_no_tool" or (
        generation == "llm"
        and not citations
        and "일반 안내" in " ".join(str(item) for item in limitations)
    )
    contract_passed = status_passed and citations_passed and generation_passed and no_tool_passed
    content_passed = include_passed and forbidden_passed

    evidence_text = ""
    if probe.last_context is not None:
        evidence = portfolio_snapshot_evidence(probe.last_context)
        evidence_text = "\n".join(item.fact for item in evidence)
    evidence_passed = all(term in evidence_text for term in case.required_evidence_terms)
    if case.expected_route != "agent":
        evidence_passed = True

    failures: list[str] = []
    if not route_passed:
        failures.append(f"expected agent calls {expected_calls}, got {probe.calls}")
    if not status_passed:
        failures.append(f"expected status {case.expected_status}, got {status}")
    if content_evaluated and not include_passed:
        failures.append("required answer points were missing")
    if content_evaluated and not forbidden_passed:
        failures.append("answer contained a forbidden assertion")
    if not citations_passed:
        failures.append("answer did not include a required source citation")
    if not generation_passed:
        failures.append("agent answer fell back instead of completing with validated LLM output")
    if not no_tool_passed:
        failures.append("expected a no-tool general guidance answer")
    if not evidence_passed:
        failures.append("required portfolio evidence was not exposed to the agent")

    passed = (
        route_passed
        and evidence_passed
        and contract_passed
        and (content_passed or not content_evaluated)
    )
    return QaEvalResult(
        case_id=case.id,
        profile=case.profile,
        passed=passed,
        route_passed=route_passed,
        contract_passed=contract_passed,
        content_evaluated=content_evaluated,
        content_passed=content_passed,
        evidence_passed=evidence_passed,
        status=status,
        generation=generation,
        agent_calls=probe.calls,
        citation_count=len(citations),
        no_tool_passed=no_tool_passed,
        elapsed_ms=elapsed_ms,
        answer=answer,
        failures=tuple(failures),
    )


def fixture_policies(path: Path = POLICY_FIXTURE) -> list[PolicyInput]:
    rows = cast(list[dict[str, object]], json.loads(path.read_text(encoding="utf-8")))
    return [PolicyInput.model_validate(row) for row in rows]


def _render_eval_output(answer: str, end_event: QaEndEvent) -> str:
    claim_channels = end_event.claim_channels
    if claim_channels is None:
        return answer
    return "\n".join(
        (
            answer,
            json.dumps(
                claim_channels.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    )


def _case_from_json(row: dict[str, object]) -> QaEvalCase:
    route = str(row["expected_route"])
    if route not in {"agent", "agent_no_tool", "input_guardrail"}:
        raise ValueError(f"unknown expected route: {route}")
    history = tuple(
        ConversationMessage.model_validate(item)
        for item in cast(list[dict[str, object]], row.get("history", []))
    )
    return QaEvalCase(
        id=str(row["id"]),
        question=str(row["question"]),
        profile=str(row["profile"]),
        expected_route=cast(EvalRoute, route),
        expected_status=str(row["expected_status"]),
        must_include_groups=tuple(
            tuple(str(term) for term in group)
            for group in cast(list[list[object]], row.get("must_include_groups", []))
        ),
        required_evidence_terms=tuple(
            str(term) for term in cast(list[object], row.get("required_evidence_terms", []))
        ),
        must_not_include=tuple(
            str(term) for term in cast(list[object], row.get("must_not_include", []))
        ),
        history=history,
        live=bool(row.get("live", False)),
        require_citations=bool(row.get("require_citations", False)),
    )


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--live-only", action="store_true")
    parser.add_argument("--show-passing", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--model")
    args = parser.parse_args()

    cases = load_cases()
    if args.live_only:
        cases = tuple(case for case in cases if case.live)
    if args.case:
        selected_ids = set(args.case)
        cases = tuple(case for case in cases if case.id in selected_ids)
    report = evaluate(cases, live=args.live, model=args.model)
    print(render_report(report, show_passing=args.show_passing))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0 if report.passed == report.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
