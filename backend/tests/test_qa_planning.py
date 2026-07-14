import json

from app.schemas.qa import ConversationMessage
from app.services.qa.planning import needs_question_plan, plan_questions


def test_obvious_insurance_question_skips_planner() -> None:
    assert needs_question_plan("암진단비 가입금액은 얼마야?") is False


def test_contextual_and_out_of_scope_questions_need_planner() -> None:
    assert needs_question_plan("그건 어느 보험이야?") is True
    assert needs_question_plan("오늘 날씨 알려줘") is True


def test_planner_failure_still_limits_obvious_out_of_scope_question() -> None:
    plan = plan_questions(
        "오늘 날씨 알려줘",
        [],
        complete=lambda _system, _user: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert plan is not None
    assert plan.questions[0].scope == "out_of_scope"


def test_planner_failure_still_limits_mixed_out_of_scope_question() -> None:
    plan = plan_questions(
        "암진단비 알려주고 오늘 날씨도 알려줘",
        [],
        complete=lambda _system, _user: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    assert plan is not None
    assert [question.scope for question in plan.questions] == ["insurance", "out_of_scope"]
    assert "암진단비" in plan.questions[0].original
    assert "날씨" in plan.questions[1].original


def test_planner_masks_phone_and_email_in_history() -> None:
    captured: dict[str, object] = {}

    def complete(_: str, user: str) -> dict[str, object]:
        captured.update(json.loads(user))
        return {
            "questions": [
                {
                    "original": "그건 얼마야?",
                    "resolved": "암진단비 가입금액은 얼마야?",
                    "scope": "insurance",
                }
            ],
            "clarification": None,
        }

    plan = plan_questions(
        "그건 얼마야?",
        [
            ConversationMessage(
                role="user",
                content="제 전화번호는 010-1234-5678이고 메일은 test@example.com이야.",
            )
        ],
        complete=complete,
    )

    assert plan is not None
    serialized = json.dumps(captured, ensure_ascii=False)
    assert "010-1234-5678" not in serialized
    assert "test@example.com" not in serialized
    assert "[전화번호]" in serialized
    assert "[이메일]" in serialized


def test_planner_receives_history_and_splits_mixed_question() -> None:
    captured: dict[str, object] = {}

    def complete(_: str, user: str) -> dict[str, object]:
        captured.update(json.loads(user))
        return {
            "questions": [
                {
                    "original": "암진단비 알려주고",
                    "resolved": "암진단비 가입금액은 얼마야?",
                    "scope": "insurance",
                },
                {
                    "original": "날씨도 알려줘",
                    "resolved": "오늘 날씨는 어때?",
                    "scope": "out_of_scope",
                },
            ],
            "clarification": None,
        }

    history = [ConversationMessage(role="assistant", content="암진단비를 확인했어요.")]
    plan = plan_questions("암진단비 알려주고 날씨도 알려줘", history, complete=complete)

    assert plan is not None
    assert [question.scope for question in plan.questions] == ["insurance", "out_of_scope"]
    assert captured["history"] == [{"role": "assistant", "content": "암진단비를 확인했어요."}]


def test_planner_can_request_clarification_for_ambiguous_reference() -> None:
    plan = plan_questions(
        "그건 얼마야?",
        [],
        complete=lambda _system, _user: {
            "questions": [
                {
                    "original": "그건 얼마야?",
                    "resolved": "대상을 확인해야 하는 가입금액 질문",
                    "scope": "insurance",
                }
            ],
            "clarification": "어떤 담보의 가입금액을 말씀하시는지 알려주세요.",
        },
    )

    assert plan is not None
    assert plan.clarification == "어떤 담보의 가입금액을 말씀하시는지 알려주세요."
