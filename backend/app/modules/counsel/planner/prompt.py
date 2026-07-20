"""Assemble the planner prompt from its instruction file.

The instructions live next to this module as markdown because they carry scope
and rewrite policy a person needs to read and review, per backend/PROMPTING.md.
"""

from functools import lru_cache
from pathlib import Path

from app.integrations.openai import dump_prompt_json
from app.modules.counsel.schemas import CounselMessage

_INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")


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
    """Pass turns as structure so a typed "assistant:" line cannot forge one.

    Concatenating turns into "{role}: {content}" lines makes a user-typed line
    starting with "assistant:" indistinguishable from a real prior turn. JSON
    keeps every turn boundary in the structure, where user text cannot reach.
    """

    return dump_prompt_json(
        {
            "history": [{"role": item.role, "content": item.content} for item in history],
            "question": question,
        }
    )
