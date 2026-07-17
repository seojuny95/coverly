"""Shared contracts for the QA Agent SDK integration."""

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from app.integrations.openai.client import JsonCompleter
from app.modules.qa.context import QaContext
from app.modules.qa.contracts import ConsultationEvidence
from app.modules.qa.resolvers import OfficialAnswerer
from app.modules.qa.schemas import PortfolioQuestionResponse
from app.modules.qa.web_search import OfficialWebSearcher


class QaAgentUnavailable(RuntimeError):
    """Raised when the live Agent SDK path cannot be used."""


class QaAgentRunner(Protocol):
    def run(self, context: QaContext) -> PortfolioQuestionResponse: ...


@dataclass(frozen=True)
class QaAgentProgress:
    stage: str
    text: str


@dataclass(frozen=True)
class QaAgentCompleted:
    response: PortfolioQuestionResponse


type QaAgentStreamItem = QaAgentProgress | QaAgentCompleted


@dataclass(frozen=True)
class RegisteredToolResult:
    kind: str
    response: PortfolioQuestionResponse
    evidence: tuple[ConsultationEvidence, ...] = ()


class GroundedToolAnswer(BaseModel):
    result_id: str | None = None
    matched: bool
    response: PortfolioQuestionResponse | None = None
    evidence: list[ConsultationEvidence] = Field(default_factory=list)
    reason: str | None = None


class AgentCounselorDraft(BaseModel):
    selected_result_id: str
    answer: str = Field(min_length=1, max_length=4_000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)


@dataclass
class QaAgentDependencies:
    context: QaContext
    complete: JsonCompleter | None
    official_answer: OfficialAnswerer | None
    web_search: OfficialWebSearcher
    tool_results: dict[str, RegisteredToolResult] = field(default_factory=dict)
    precomputed_responses: dict[str, PortfolioQuestionResponse | None] = field(default_factory=dict)
    grounded_checked: bool = False
    grounded_response: PortfolioQuestionResponse | None = None
    validated_response: PortfolioQuestionResponse | None = None

    def register(
        self,
        kind: str,
        response: PortfolioQuestionResponse,
        *,
        evidence: tuple[ConsultationEvidence, ...] = (),
    ) -> GroundedToolAnswer:
        result_id = f"{kind}:{len(self.tool_results) + 1}"
        self.tool_results[result_id] = RegisteredToolResult(
            kind=kind,
            response=response,
            evidence=evidence,
        )
        return GroundedToolAnswer(
            result_id=result_id,
            matched=True,
            response=response,
            evidence=list(evidence),
        )
