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
    rewritten_question: str
    in_scope: bool
    excluded_note: str | None = None
    reason: str
    tasks: list[CounselTask] = Field(default_factory=list)
    response_mode: CounselResponseMode = "agent"

    @property
    def requested_coverage_names(self) -> list[str]:
        """Every coverage name this plan asks the fact modules to look up."""

        return [name for task in self.tasks for name in task.coverage_names]
