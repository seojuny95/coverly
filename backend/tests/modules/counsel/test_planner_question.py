from app.modules.counsel.planner import CounselPlan


def _plan(**overrides: object) -> CounselPlan:
    base: dict[str, object] = {
        "question_without_history": "이번 질문만 정리한 문장",
        "rewritten_question": "이전 대화로 복원한 문장",
        "needs_history": False,
        "in_scope": True,
        "reason": "보험 질문",
    }
    return CounselPlan.model_validate(base | overrides)


def test_a_self_contained_question_ignores_the_history_resolved_rewrite() -> None:
    # The planner can quietly replace an off-topic question with an earlier one.
    # When it says the turn stands on its own, the version written without any
    # history is the one to answer -- it cannot have borrowed from an old topic.
    plan = _plan(needs_history=False)

    assert plan.question_to_answer == "이번 질문만 정리한 문장"


def test_a_question_that_points_backwards_uses_the_resolved_rewrite() -> None:
    plan = _plan(needs_history=True)

    assert plan.question_to_answer == "이전 대화로 복원한 문장"


def test_an_out_of_scope_turn_keeps_its_own_question() -> None:
    plan = _plan(
        needs_history=False,
        in_scope=False,
        question_without_history="오늘 서울 날씨 어때?",
        rewritten_question="교통사고처리지원금 얼마야?",
    )

    assert plan.question_to_answer == "오늘 서울 날씨 어때?"
