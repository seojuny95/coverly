"""Local context passed to the qa agent run."""

from collections.abc import Callable
from dataclasses import dataclass

from app.modules.portfolio.schemas import PolicyInput
from app.rag.official.evidence import OfficialEvidenceResult
from app.rag.policy.evidence import PolicyEvidenceResult

OfficialEvidenceRetriever = Callable[[str], OfficialEvidenceResult]
PolicyEvidenceRetriever = Callable[[tuple[str, ...], str, str], PolicyEvidenceResult]


@dataclass
class QaContext:
    policies: list[PolicyInput]
    current_question: str = ""
    policy_rag_session_ids: tuple[str, ...] = ()
    trace_thread_id: str | None = None
    trace_request_id: str = ""
    official_evidence_retriever: OfficialEvidenceRetriever | None = None
    policy_evidence_retriever: PolicyEvidenceRetriever | None = None
