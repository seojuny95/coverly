"""Validated contracts for the Agent+RAG evaluation dataset."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QaRagTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    required_tools: list[str] = Field(default_factory=list)
    required_tool_groups: list[list[str]] = Field(default_factory=list)
    required_tool_order: list[str] = Field(default_factory=list)
    minimum_tool_calls: dict[str, int] = Field(default_factory=dict)
    forbidden_tools: list[str] = Field(default_factory=list)
    include_all: list[str] = Field(default_factory=list)
    include_any: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    expect_in_scope: bool | None = None
    expect_source: bool = False
    judge: list[str] = Field(default_factory=list)
    reference_facts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_tool_expectations(self) -> QaRagTurn:
        if any(not group for group in self.required_tool_groups):
            raise ValueError("required tool groups must not be empty")
        if any(count < 1 for count in self.minimum_tool_calls.values()):
            raise ValueError("minimum tool call counts must be positive")

        required = set(self.required_tools)
        forbidden = set(self.forbidden_tools)
        overlap = required & forbidden
        if overlap:
            raise ValueError(f"tools cannot be both required and forbidden: {sorted(overlap)}")
        return self


class QaRagCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    set: Literal["practice", "test"] = "practice"
    tags: list[str] = Field(min_length=1)
    turns: list[QaRagTurn] = Field(min_length=1)


class QaRagDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    fixture: str = Field(min_length=1)
    policy_retrieval_dataset: str = Field(min_length=1)
    policy_session_ids: list[str] = Field(min_length=1)
    judge_rubrics: dict[str, str]
    cases: list[QaRagCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identifiers(self) -> QaRagDataset:
        case_ids = [case.id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Agent+RAG case ids must be unique")
        if len(self.policy_session_ids) != len(set(self.policy_session_ids)):
            raise ValueError("Policy RAG session ids must be unique")

        known_rubrics = set(self.judge_rubrics)
        unknown_rubrics = {
            rubric
            for case in self.cases
            for turn in case.turns
            for rubric in turn.judge
            if rubric not in known_rubrics
        }
        if unknown_rubrics:
            raise ValueError(f"unknown Agent+RAG judge rubrics: {sorted(unknown_rubrics)}")
        return self


def load_qa_rag_dataset(path: Path) -> QaRagDataset:
    return QaRagDataset.model_validate_json(path.read_text(encoding="utf-8"))


def case_payload(case: QaRagCase) -> dict[str, object]:
    return cast(dict[str, object], case.model_dump(exclude_none=True))
