"""Assemble the planner prompt from its instruction file.

The instructions live next to this module as markdown because they carry scope
and rewrite policy a person needs to read and review, per backend/PROMPTING.md.
"""

from functools import lru_cache
from pathlib import Path

from app.modules.counsel.schemas import CounselMessage

_INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")
_NO_HISTORY = "(이전 대화 없음)"


@lru_cache(maxsize=1)
def build_system_prompt() -> str:
    """Return the planner instructions.

    The user's coverage list is deliberately NOT included. Measured on the eval
    set, showing it made the model treat "no matching coverage" as "out of
    scope", refusing questions such as "치아 임플란트 보장도 들어있어?" that the
    product exists to answer. Coverage identity is resolved after planning
    instead, by canonical matching and the escalation gate.
    """

    return _INSTRUCTIONS_PATH.read_text(encoding="utf-8")


def build_user_prompt(question: str, history: list[CounselMessage]) -> str:
    history_text = (
        "\n".join(f"{item.role}: {item.content}" for item in history) if history else _NO_HISTORY
    )
    return f"이전 대화:\n{history_text}\n\n질문: {question}"
