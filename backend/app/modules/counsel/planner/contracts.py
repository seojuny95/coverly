"""Typed contracts for one planned counsel turn."""

from typing import Literal

from pydantic import BaseModel, Field

CounselTaskKind = Literal[
    "policy_count",
    "policy_list",
    "coverage_list",
    "coverage_lookup",
    "coverage_total",
    "overlap_check",
    "claim_channel",
    "portfolio_review",
]
CounselResponseMode = Literal[
    "agent",
    "fact_only",
    "fact_then_explanation",
    "clarify",
    "out_of_scope",
]


class CounselTask(BaseModel):
    kind: CounselTaskKind
    coverage_names: list[str] = Field(default_factory=list)
    focus: str | None = None


class CounselPlan(BaseModel):
    # Declaration order is generation order for structured output, so it follows
    # instructions.md: the model decides whether it needs the conversation before
    # it writes the sentence that uses one.
    question_without_history: str = ""
    """The turn tidied up on its own, with nothing borrowed from earlier turns."""

    needs_history: bool = True
    """Whether this turn can only be understood by looking at earlier turns.

    Defaults to true so a plan that carries only one rewrite -- an older
    payload, a test fixture -- answers the rewritten question as before.
    """

    rewritten_question: str
    """The turn with its back-references resolved from the conversation."""

    excluded_note: str | None = None
    in_scope: bool
    reason: str
    tasks: list[CounselTask] = Field(default_factory=list)
    response_mode: CounselResponseMode = "agent"

    @property
    def question_to_answer(self) -> str:
        """The question this turn actually answers.

        Asking for both versions is what keeps a changed topic intact. A single
        rewrite has to fold the conversation into one sentence, and when it
        cannot, it substitutes the earlier question instead -- "오늘 날씨 어때?"
        came back as an answer about 교통사고처리지원금. The history-free version
        cannot borrow from an old topic because it was written without seeing one.
        """

        if self.needs_history or not self.question_without_history:
            return self.rewritten_question
        return self.question_without_history

    @property
    def requested_coverage_names(self) -> list[str]:
        """Every coverage name this plan asks the fact modules to look up."""

        return [name for task in self.tasks for name in task.coverage_names]
