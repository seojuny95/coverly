from app.modules.counsel.answer.clarify import compose_clarify_question
from app.modules.counsel.answer.executor import execute_fact_tasks
from app.modules.counsel.planner import CounselPlan, CounselTask
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


def _plan(*tasks: CounselTask) -> CounselPlan:
    return CounselPlan(
        rewritten_question="질문",
        in_scope=True,
        reason="보험 질문",
        response_mode="clarify",
        tasks=list(tasks),
    )


def test_candidates_become_the_question_the_user_is_asked() -> None:
    plan = _plan(CounselTask(kind="coverage_lookup", coverage_names=["암진단비"]))

    question = compose_clarify_question(execute_fact_tasks(plan, _policies()))

    assert question is not None
    assert "암진단비(유사암제외)" in question
    assert "유사암진단비" in question
    assert question.rstrip().endswith("?")


def test_a_turn_with_nothing_to_narrow_asks_what_to_look_up() -> None:
    question = compose_clarify_question(execute_fact_tasks(_plan(), _policies()))

    assert question is not None
    assert question.rstrip().endswith("?")


def test_resolved_facts_need_no_clarifying_question() -> None:
    plan = _plan(CounselTask(kind="coverage_lookup", coverage_names=["암진단비(유사암제외)"]))

    assert compose_clarify_question(execute_fact_tasks(plan, _policies())) is None


def test_an_unresolvable_name_with_no_candidates_defers_to_the_agent() -> None:
    # "심장 쪽" shares no spelling with 허혈성심질환진단비, so we have no candidate to
    # offer. A generic ask-back would be worse than letting the agent interpret it.
    plan = _plan(CounselTask(kind="coverage_lookup", coverage_names=["심장 쪽 담보"]))

    assert compose_clarify_question(execute_fact_tasks(plan, _policies())) is None
