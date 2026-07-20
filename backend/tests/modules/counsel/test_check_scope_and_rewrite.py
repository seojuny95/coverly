from app.modules.counsel.check_scope_and_rewrite import check_scope_and_rewrite
from app.modules.counsel.schemas import CounselMessage


def test_no_history_returns_the_original_question_and_scope_decision() -> None:
    def fake(_system: str, _user: str) -> dict[str, object]:
        return {"rewritten_question": "암진단비 알려줘", "in_scope": True, "reason": "보험 질문"}

    result = check_scope_and_rewrite("암진단비 알려줘", [], complete=fake)

    assert result.rewritten_question == "암진단비 알려줘"
    assert result.in_scope is True


def test_with_history_rewrites_and_classifies_in_one_call() -> None:
    captured: dict[str, str] = {}

    def fake(_system: str, user: str) -> dict[str, object]:
        captured["user"] = user
        return {
            "rewritten_question": "암진단비 청구는 어떻게 하나요?",
            "in_scope": True,
            "reason": "보험 질문",
        }

    history = [
        CounselMessage(role="user", content="대장암 진단을 받았어"),
        CounselMessage(role="assistant", content="암진단비가 확인돼요."),
    ]
    result = check_scope_and_rewrite("청구는 어떻게 해?", history, complete=fake)

    assert result.rewritten_question == "암진단비 청구는 어떻게 하나요?"
    assert "대장암" in captured["user"]


def test_unrelated_question_is_classified_out_of_scope() -> None:
    def fake(_system: str, _user: str) -> dict[str, object]:
        return {"rewritten_question": "오늘 날씨 알려줘", "in_scope": False, "reason": "무관"}

    result = check_scope_and_rewrite("오늘 날씨 알려줘", [], complete=fake)

    assert result.in_scope is False


def test_excluded_note_defaults_to_none_when_the_model_omits_it() -> None:
    def fake(_system: str, _user: str) -> dict[str, object]:
        return {"rewritten_question": "암진단비 알려줘", "in_scope": True, "reason": "보험 질문"}

    result = check_scope_and_rewrite("암진단비 알려줘", [], complete=fake)

    assert result.excluded_note is None


def test_excluded_note_carries_the_dropped_out_of_scope_part_of_a_mixed_question() -> None:
    def fake(_system: str, _user: str) -> dict[str, object]:
        return {
            "rewritten_question": "암진단비 합계를 알려줘.",
            "in_scope": True,
            "excluded_note": "오늘 날씨는 보험과 무관해 답변에서 뺐습니다.",
            "reason": "보험 질문 + 무관한 질문 혼합",
        }

    result = check_scope_and_rewrite("암진단비 합계 알려주고 오늘 날씨도 알려줘", [], complete=fake)

    assert result.excluded_note == "오늘 날씨는 보험과 무관해 답변에서 뺐습니다."
