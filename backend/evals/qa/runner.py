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
from app.modules.qa.agent import build_qa_agent_runner
from app.modules.qa.agent_contracts import AgentCounselorDraft, QaAgentDependencies, QaAgentRunner
from app.modules.qa.agent_evidence import consultation_evidence, portfolio_snapshot_evidence
from app.modules.qa.agent_validation import validated_agent_response
from app.modules.qa.context import QaContext
from app.modules.qa.resolvers import context_fallback, resolve_precomputed_answer
from app.modules.qa.schemas import ConversationMessage, PortfolioQuestionResponse
from app.modules.qa.service import stream_portfolio_answer
from app.modules.qa.web_search import WebSearchResult
from app.rag.official.answer import answer_official_question
from app.rag.policy import generate_policy_answer

EVAL_FIXTURE = Path(__file__).resolve().parent / "dataset.json"
POLICY_FIXTURE = Path(__file__).resolve().parent / "fixture_policies.json"
EvalRoute = Literal["fast", "agent", "agent_no_tool", "planned", "scope"]

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
    answer_evaluated: bool
    answer_passed: bool
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
    answer_evaluated: int
    answer_passed: int
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
        delegate: QaAgentRunner | None = None,
    ) -> None:
        self.expected_route = expected_route
        self.delegate = delegate
        self.calls = 0
        self.last_context: QaContext | None = None

    def run(self, context: QaContext) -> PortfolioQuestionResponse:
        self.calls += 1
        self.last_context = context
        if self.delegate is not None:
            return self.delegate.run(context)

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

        deterministic = resolve_precomputed_answer(
            context,
            try_official=False,
            official_answer=None,
            default_official_answer=answer_official_question,
            complete=None,
            pass_complete=False,
            retrieve_policy=lambda _ids, _question: [],
            generate_policy=generate_policy_answer,
        )
        if deterministic is not None:
            return deterministic

        evidence = consultation_evidence(context)
        citations = [citation_from_evidence(item) for item in evidence[:3]]
        if not citations:
            return context_fallback(context)
        return PortfolioQuestionResponse(
            status="answered",
            answer="복합 상담은 Agent 경로에서 관련 근거를 사용해 답합니다.",
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
    evaluated = tuple(result for result in results if result.answer_evaluated)
    return QaEvalReport(
        mode="live" if live else "baseline",
        passed=sum(result.passed for result in results),
        total=len(results),
        answer_evaluated=len(evaluated),
        answer_passed=sum(result.answer_passed for result in evaluated),
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
            f"answers={report.answer_passed}/{report.answer_evaluated} "
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
    probe = _ProbeAgent(expected_route=case.expected_route, delegate=delegate)
    started = perf_counter()
    try:
        events = list(
            stream_portfolio_answer(
                case.question,
                fixture_policies(),
                history=list(case.history),
                agent_runner=probe,
            )
        )
        elapsed_ms = (perf_counter() - started) * 1000
        answer = "".join(str(event.get("text", "")) for event in events)
        end = events[-1]
        status = str(end.get("status", "unknown"))
        generation = str(end.get("generation", "fallback"))
        citations = cast(list[object], end.get("citations", []))
        rendered_output = _render_eval_output(answer, end)
    except Exception as exc:
        elapsed_ms = (perf_counter() - started) * 1000
        return QaEvalResult(
            case_id=case.id,
            profile=case.profile,
            passed=False,
            route_passed=False,
            answer_evaluated=live or case.expected_route != "agent",
            answer_passed=False,
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

    expected_calls = 0 if case.expected_route in {"planned", "scope"} else 1
    route_passed = probe.calls == expected_calls
    answer_evaluated = live or case.expected_route != "agent"
    include_passed = all(
        any(term in rendered_output for term in group) for group in case.must_include_groups
    )
    forbidden = (*_UNIVERSAL_FORBIDDEN, *case.must_not_include)
    forbidden_passed = all(term not in answer for term in forbidden)
    status_passed = status == case.expected_status
    citations_passed = not case.require_citations or bool(citations)
    generation_passed = not (live and case.expected_route == "agent") or generation == "llm"
    limitations = cast(list[object], end.get("limitations", []))
    no_tool_passed = case.expected_route != "agent_no_tool" or (
        generation == "llm"
        and not citations
        and "일반 안내" in " ".join(str(item) for item in limitations)
    )
    answer_passed = (
        status_passed
        and include_passed
        and forbidden_passed
        and citations_passed
        and generation_passed
        and no_tool_passed
    )

    evidence_text = ""
    if probe.last_context is not None:
        evidence = consultation_evidence(probe.last_context) or portfolio_snapshot_evidence(
            probe.last_context
        )
        evidence_text = "\n".join(item.fact for item in evidence)
    evidence_passed = all(term in evidence_text for term in case.required_evidence_terms)
    if case.expected_route != "agent":
        evidence_passed = True

    failures: list[str] = []
    if not route_passed:
        failures.append(f"expected agent calls {expected_calls}, got {probe.calls}")
    if answer_evaluated and not status_passed:
        failures.append(f"expected status {case.expected_status}, got {status}")
    if answer_evaluated and not include_passed:
        failures.append("required answer points were missing")
    if answer_evaluated and not forbidden_passed:
        failures.append("answer contained a forbidden assertion")
    if answer_evaluated and not citations_passed:
        failures.append("answer did not include a required source citation")
    if answer_evaluated and not generation_passed:
        failures.append("agent answer fell back instead of completing with validated LLM output")
    if answer_evaluated and not no_tool_passed:
        failures.append("expected a no-tool general guidance answer")
    if not evidence_passed:
        failures.append("required portfolio evidence was not exposed to the agent")

    passed = route_passed and evidence_passed and (answer_passed or not answer_evaluated)
    return QaEvalResult(
        case_id=case.id,
        profile=case.profile,
        passed=passed,
        route_passed=route_passed,
        answer_evaluated=answer_evaluated,
        answer_passed=answer_passed,
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


def _render_eval_output(answer: str, end_event: dict[str, object]) -> str:
    claim_channels = end_event.get("claim_channels")
    if claim_channels is None:
        return answer
    return "\n".join(
        (
            answer,
            json.dumps(claim_channels, ensure_ascii=False, sort_keys=True),
        )
    )


def _case_from_json(row: dict[str, object]) -> QaEvalCase:
    route = str(row["expected_route"])
    if route not in {"fast", "agent", "agent_no_tool", "planned", "scope"}:
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
