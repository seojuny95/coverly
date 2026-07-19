"""Shared contracts for the QA Agent SDK integration."""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from app.integrations.openai.client import JsonCompleter
from app.modules.consultation.contracts import ConsultationEvidence
from app.modules.qa.context import QaContext
from app.modules.qa.schemas import PortfolioQuestionResponse
from app.modules.qa.tools.web_search import OfficialWebSearcher
from app.rag.official.answer import RagAnswer


class QaAgentUnavailable(RuntimeError):
    """Raised when the live Agent SDK path cannot be used."""


class QaAgentRunner(Protocol):
    def run(self, context: QaContext) -> PortfolioQuestionResponse: ...


class OfficialAnswerer(Protocol):
    def __call__(self, question: str) -> RagAnswer: ...


@dataclass(frozen=True)
class QaAgentProgress:
    stage: str
    text: str


@dataclass(frozen=True)
class QaAgentMeta:
    status: str  # PortfolioQuestionResponse.status
    generation: str  # "llm" | "fallback"


@dataclass(frozen=True)
class QaAgentDelta:
    text: str


@dataclass(frozen=True)
class QaAgentCompleted:
    response: PortfolioQuestionResponse


type QaAgentStreamItem = QaAgentProgress | QaAgentMeta | QaAgentDelta | QaAgentCompleted


@dataclass(frozen=True)
class RegisteredToolResult:
    kind: str
    response: PortfolioQuestionResponse
    evidence: tuple[ConsultationEvidence, ...] = ()
    trust_level: Literal["deterministic", "generated"] = "generated"


@dataclass(frozen=True)
class ToolFailure:
    kind: str
    reason: str


class GroundedToolAnswer(BaseModel):
    result_id: str | None = None
    matched: bool
    response: PortfolioQuestionResponse | None = None
    evidence: list[ConsultationEvidence] = Field(default_factory=list)
    reason: str | None = None


class AgentCounselorDraft(BaseModel):
    answer_mode: Literal[
        "tool_grounded",
        "general_guidance",
        "insufficient_evidence",
        "out_of_scope",
    ] = "tool_grounded"
    selected_result_id: str | None = None
    answer: str = Field(min_length=1, max_length=4_000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("selected_result_id", mode="before")
    @classmethod
    def _blank_selection_is_none(cls, value: object) -> object:
        """Canonicalize "no selection" to None.

        Models emit an empty or whitespace string instead of null when they use
        no single tool result (multi-tool synthesis). Downstream grounding gates
        all test ``selected_result_id is None``, so normalize blanks to None here
        rather than duplicating the check at every call site.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


class QaInputDecision(BaseModel):
    """Structured input-guardrail decision without keyword routing."""

    scope: Literal["insurance", "coverly", "greeting", "mixed", "out_of_scope"]
    should_block: bool
    requires_fresh_official_source: bool
    requires_uploaded_policy_terms: bool = False
    is_situational: bool = False
    insurance_request: str | None = Field(max_length=500)
    out_of_scope_request: str | None = Field(max_length=500)
    reason: str = Field(min_length=1, max_length=240)


@dataclass
class QaAgentDependencies:
    context: QaContext
    complete: JsonCompleter | None
    official_answer: OfficialAnswerer | None
    web_search: OfficialWebSearcher
    classify_input: JsonCompleter | None = None
    input_decision: QaInputDecision | None = None
    tool_results: dict[str, RegisteredToolResult] = field(default_factory=dict)
    tool_failures: list[ToolFailure] = field(default_factory=list)
    validated_response: PortfolioQuestionResponse | None = None

    def unmatched(self, kind: str, reason: str) -> GroundedToolAnswer:
        self.tool_failures.append(ToolFailure(kind=kind, reason=reason))
        return GroundedToolAnswer(matched=False, reason=reason)

    def register(
        self,
        kind: str,
        response: PortfolioQuestionResponse,
        *,
        evidence: tuple[ConsultationEvidence, ...] = (),
        trust_level: Literal["deterministic", "generated"] = "generated",
    ) -> GroundedToolAnswer:
        result_id = f"{kind}:{len(self.tool_results) + 1}"
        self.tool_results[result_id] = RegisteredToolResult(
            kind=kind,
            response=response,
            evidence=evidence,
            trust_level=trust_level,
        )
        return GroundedToolAnswer(
            result_id=result_id,
            matched=True,
            response=response,
            evidence=list(evidence),
        )
