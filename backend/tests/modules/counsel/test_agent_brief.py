from app.modules.counsel.answer.brief import build_agent_input
from app.modules.counsel.schemas import CounselMessage


def _history() -> list[CounselMessage]:
    return [
        CounselMessage(role="user", content="암진단비(유사암제외) 얼마야?"),
        CounselMessage(role="assistant", content="2,000만원이에요."),
    ]


def test_earlier_turns_keep_their_roles_instead_of_becoming_one_blob() -> None:
    # Flattening the conversation into a single user message makes every past
    # line read as something the user is asking right now.
    items = build_agent_input(
        "그거 어디에 청구해?",
        history=_history(),
        facts=None,
        facts_shown=False,
        needs_hedge=False,
    )

    assert [item["role"] for item in items] == ["user", "assistant", "user"]
    assert items[0]["content"] == "암진단비(유사암제외) 얼마야?"
    assert "그거 어디에 청구해?" in str(items[-1]["content"])


def test_the_current_question_is_always_last() -> None:
    items = build_agent_input(
        "지금 질문",
        history=_history(),
        facts="확인된 사실",
        facts_shown=False,
        needs_hedge=False,
    )

    assert items[-1]["role"] == "user"
    assert "지금 질문" in str(items[-1]["content"])
    assert "확인된 사실" in str(items[-1]["content"])


def test_a_first_turn_carries_no_earlier_messages() -> None:
    items = build_agent_input(
        "첫 질문",
        history=[],
        facts=None,
        facts_shown=False,
        needs_hedge=False,
    )

    assert len(items) == 1
    assert items[0]["content"] == "첫 질문"


def test_the_current_turn_says_what_was_shown_and_whether_to_hedge() -> None:
    def current(facts_shown: bool, needs_hedge: bool) -> str:
        items = build_agent_input(
            "질문",
            history=[],
            facts="사실",
            facts_shown=facts_shown,
            needs_hedge=needs_hedge,
        )
        return str(items[-1]["content"])

    assert "이미 사용자에게" in current(facts_shown=True, needs_hedge=False)
    assert "금액을 확정해서" not in current(facts_shown=True, needs_hedge=False)
    assert "금액을 확정해서" in current(facts_shown=True, needs_hedge=True)
