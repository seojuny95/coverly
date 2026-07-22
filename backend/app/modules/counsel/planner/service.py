"""LLM-backed turn planner for grounded counsel answers."""

from app.integrations.openai.client import JsonCompleter
from app.modules.counsel.planner.contracts import CounselPlan
from app.modules.counsel.planner.prompt import build_system_prompt, build_user_prompt
from app.modules.qa.schemas import CounselMessage


def plan_counsel_turn(
    question: str,
    history: list[CounselMessage],
    *,
    complete: JsonCompleter,
) -> CounselPlan:
    """Rewrite, scope-check, and plan the counsel turn in one structured LLM call."""

    raw = complete(
        build_system_prompt(),
        build_user_prompt(question, history),
    )
    plan = CounselPlan.model_validate(raw)
    if not plan.in_scope:
        return plan.model_copy(update={"tasks": [], "response_mode": "out_of_scope"})
    return plan
