"""How much of the conversation a turn is allowed to see.

The client sends the history, so without a bound a single request can carry an
arbitrarily long conversation into every model call. Keeping a window also
limits how far an old topic can reach into the current answer.
"""

from app.modules.qa.schemas import CounselMessage


def recent_turns(history: list[CounselMessage], *, max_turns: int) -> list[CounselMessage]:
    """Return the last `max_turns` turns.

    A turn is one user message and everything that followed it, so an answer is
    never separated from the question it belongs to. Messages before the first
    kept question are dropped, including an answer whose question is already out
    of the window.
    """

    if max_turns <= 0:
        return []

    question_positions = [index for index, message in enumerate(history) if message.role == "user"]
    if len(question_positions) <= max_turns:
        return history[question_positions[0] :] if question_positions else []

    return history[question_positions[-max_turns] :]
