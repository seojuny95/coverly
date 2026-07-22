from app.modules.qa.history import recent_turns
from app.modules.qa.schemas import CounselMessage


def _exchange(index: int) -> list[CounselMessage]:
    return [
        CounselMessage(role="user", content=f"질문{index}"),
        CounselMessage(role="assistant", content=f"답변{index}"),
    ]


def _conversation(count: int) -> list[CounselMessage]:
    return [message for index in range(1, count + 1) for message in _exchange(index)]


def test_only_the_most_recent_turns_are_kept() -> None:
    kept = recent_turns(_conversation(5), max_turns=2)

    assert [message.content for message in kept] == ["질문4", "답변4", "질문5", "답변5"]


def test_a_short_conversation_is_left_alone() -> None:
    history = _conversation(2)

    assert recent_turns(history, max_turns=5) == history


def test_a_turn_keeps_everything_that_followed_the_question() -> None:
    # A turn is one user message and everything after it, so an answer is never
    # separated from the question it belongs to.
    history = [
        *_exchange(1),
        CounselMessage(role="user", content="질문2"),
        CounselMessage(role="assistant", content="답변2-a"),
        CounselMessage(role="assistant", content="답변2-b"),
    ]

    kept = recent_turns(history, max_turns=1)

    assert [message.content for message in kept] == ["질문2", "답변2-a", "답변2-b"]


def test_history_that_starts_mid_turn_does_not_keep_an_orphaned_answer() -> None:
    history = [
        CounselMessage(role="assistant", content="앞선 답변"),
        *_exchange(1),
    ]

    kept = recent_turns(history, max_turns=1)

    assert [message.content for message in kept] == ["질문1", "답변1"]


def test_no_turns_means_no_history() -> None:
    assert recent_turns(_conversation(3), max_turns=0) == []
