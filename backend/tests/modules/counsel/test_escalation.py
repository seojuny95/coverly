from app.modules.counsel.answer.brief import build_agent_input
from app.modules.counsel.answer.composer import compose_fact_answer
from app.modules.counsel.answer.escalation import AnswerRoute, route_answer
from app.modules.counsel.answer.executor import execute_fact_tasks
from app.modules.counsel.planner import (
    CounselPlan,
    CounselResponseMode,
    CounselTask,
    CounselTaskKind,
)
from app.modules.portfolio.schemas import PolicyInput


def _policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "테스트보험사", "상품명": "건강보험"},
                "보장목록": [
                    {
                        "담보명": "암진단비(유사암제외)",
                        "가입금액": "2,000만원",
                        "가입금액숫자": 20_000_000,
                        "지급유형": "정액",
                    },
                    {
                        "담보명": "유사암진단비",
                        "가입금액": "1,000만원",
                        "가입금액숫자": 10_000_000,
                        "지급유형": "정액",
                    },
                ],
            }
        ),
    ]


def _route(
    question: str,
    coverage_names: list[str],
    mode: CounselResponseMode = "fact_only",
    kind: CounselTaskKind = "coverage_lookup",
) -> AnswerRoute:
    plan = CounselPlan(
        rewritten_question=question,
        in_scope=True,
        reason="보험 질문",
        response_mode=mode,
        tasks=[CounselTask(kind=kind, coverage_names=coverage_names)],
    )
    execution = execute_fact_tasks(plan, _policies())
    composed = compose_fact_answer(execution)
    return route_answer(plan, execution, composed, asked_texts=(question,))


def test_named_coverage_answers_from_facts_without_the_agent() -> None:
    route = _route("암진단비(유사암제외) 얼마야?", ["암진단비(유사암제외)"])

    assert route.fact_answer is not None
    assert "2,000만원" in route.fact_answer
    assert route.run_agent is False


def test_spacing_difference_still_counts_as_the_user_naming_the_coverage() -> None:
    route = _route("암 진단비(유사암 제외) 얼마야?", ["암진단비(유사암제외)"])

    assert route.fact_answer is not None
    assert route.run_agent is False


def test_coverage_inferred_from_a_disease_never_states_the_amount() -> None:
    # The user said "갑상선암", not a coverage name. Which coverage applies depends on
    # the policy wording, so the amounts must not be presented as the settled answer.
    route = _route("갑상선암 걸리면 얼마 받아?", ["암진단비(유사암제외)"])

    assert route.fact_answer is None
    assert route.run_agent is True


def test_unresolved_name_shows_candidates_and_still_hands_off_to_the_agent() -> None:
    # "암진단비" resolves to nothing exactly, so the turn must not end on a dead end.
    route = _route("암진단비 얼마야?", ["암진단비"])

    assert route.fact_answer is not None
    assert route.run_agent is True


def test_agent_mode_keeps_the_facts_instead_of_discarding_them() -> None:
    route = _route("암진단비(유사암제외) 보장이 충분한가?", ["암진단비(유사암제외)"], mode="agent")

    assert route.fact_answer is not None
    assert route.run_agent is True


def test_task_without_coverage_names_is_treated_as_user_directed() -> None:
    route = _route("보험 몇 개야?", [], kind="policy_count")

    assert route.fact_answer is not None
    assert route.run_agent is False


def test_unresolved_name_asks_the_agent_not_to_state_an_amount() -> None:
    route = _route("대장암 진단비 얼마야?", ["대장암 진단비"])

    assert route.run_agent is True
    assert route.needs_hedge is True


def test_named_and_resolved_coverage_needs_no_hedge() -> None:
    route = _route("암진단비(유사암제외) 얼마야?", ["암진단비(유사암제외)"])

    assert route.needs_hedge is False


def test_agent_input_carries_what_was_shown_and_whether_to_hedge() -> None:
    shown = build_agent_input("질문", facts="사실", facts_shown=True, needs_hedge=False)
    hedged = build_agent_input("질문", facts="사실", facts_shown=True, needs_hedge=True)
    plain = build_agent_input("질문", facts=None, facts_shown=False, needs_hedge=False)

    assert "이미 사용자에게" in shown
    assert "금액을 확정해서" not in shown
    assert "금액을 확정해서" in hedged
    assert plain == "질문"


def test_llm_rewrite_alone_is_not_evidence_the_user_named_the_coverage() -> None:
    # The planner may rewrite "갑상선암 걸리면?" into a coverage name. That is the
    # model's own inference, so it must not unlock a settled amount.
    plan = CounselPlan(
        rewritten_question="암진단비(유사암제외) 보장금액은 얼마인가요?",
        in_scope=True,
        reason="보험 질문",
        response_mode="fact_only",
        tasks=[CounselTask(kind="coverage_lookup", coverage_names=["암진단비(유사암제외)"])],
    )
    execution = execute_fact_tasks(plan, _policies())
    composed = compose_fact_answer(execution)

    route = route_answer(plan, execution, composed, asked_texts=("갑상선암 걸리면 얼마 받아?",))

    assert route.fact_answer is None
    assert route.run_agent is True
    assert route.needs_hedge is True


def test_a_coverage_named_in_an_earlier_user_turn_still_counts_as_named() -> None:
    plan = CounselPlan(
        rewritten_question="암진단비(유사암제외)는 어디에 청구하나요?",
        in_scope=True,
        reason="보험 질문",
        response_mode="fact_only",
        tasks=[CounselTask(kind="coverage_lookup", coverage_names=["암진단비(유사암제외)"])],
    )
    execution = execute_fact_tasks(plan, _policies())
    composed = compose_fact_answer(execution)

    route = route_answer(
        plan,
        execution,
        composed,
        asked_texts=("그거 어디에 청구해?", "암진단비(유사암제외) 얼마야?"),
    )

    assert route.fact_answer is not None
    assert route.run_agent is False
