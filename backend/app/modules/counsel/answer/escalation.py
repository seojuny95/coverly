"""Decide whether a turn may answer from deterministic facts alone.

Facts are only safe to state as settled when the user pointed at the coverage
themselves and every requested name resolved. Anything else -- a coverage the
planner inferred from a disease or situation, a name that did not match, a task
that produced nothing -- goes to the agent, which can say what is confirmed,
what is general guidance, and what still needs the policy wording.
"""

from dataclasses import dataclass

from app.modules.counsel.answer.executor import FactExecution
from app.modules.counsel.planner import CounselPlan
from app.modules.coverage.matching import query_contains_canonical_name

_FACT_FIRST_MODES = {"fact_only", "fact_then_explanation"}


@dataclass(frozen=True)
class AnswerRoute:
    """How this turn should be answered."""

    fact_answer: str | None
    """Deterministic text to stream to the user, or None to show nothing yet."""

    run_agent: bool

    needs_hedge: bool
    """True when the agent has to interpret which coverage applies, so it must not
    present an amount as the settled answer."""

    @property
    def shows_facts(self) -> bool:
        return self.fact_answer is not None


def route_answer(
    plan: CounselPlan,
    execution: FactExecution,
    fact_answer: str | None,
    *,
    asked_texts: tuple[str, ...],
) -> AnswerRoute:
    """Choose between answering from facts, handing off to the agent, or both."""

    if fact_answer is None:
        return AnswerRoute(fact_answer=None, run_agent=True, needs_hedge=False)

    if not _user_pointed_at_every_coverage(plan, asked_texts):
        # The coverage was inferred, so its amounts are not a settled answer to
        # what the user actually asked. Let the agent frame them instead.
        return AnswerRoute(fact_answer=None, run_agent=True, needs_hedge=True)

    if execution.has_unresolved_names:
        # A name that did not resolve means the agent still has to work out which
        # coverage the user meant, which is interpretation, not a confirmed fact.
        return AnswerRoute(fact_answer=fact_answer, run_agent=True, needs_hedge=True)

    if plan.response_mode in _FACT_FIRST_MODES:
        return AnswerRoute(
            fact_answer=fact_answer,
            run_agent=plan.response_mode == "fact_then_explanation",
            needs_hedge=False,
        )

    return AnswerRoute(fact_answer=fact_answer, run_agent=True, needs_hedge=False)


def _user_pointed_at_every_coverage(plan: CounselPlan, asked_texts: tuple[str, ...]) -> bool:
    """True when every planned coverage name literally appears in what was asked.

    Matching is canonical, so spacing and notation differences still count as the
    user naming the coverage, while a look-alike name does not.
    """

    for name in plan.requested_coverage_names:
        if not any(query_contains_canonical_name(text, name) for text in asked_texts):
            return False
    return True
