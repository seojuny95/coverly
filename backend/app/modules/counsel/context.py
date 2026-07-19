"""Local context passed to the counsel agent run."""

from collections.abc import Callable
from dataclasses import dataclass

from app.modules.portfolio.schemas import PolicyInput
from app.rag.official.answer import RagAnswer
from app.rag.policy.generation import PolicyGenerationResult

OfficialAnswerer = Callable[[str], RagAnswer]
PolicyTermsAnswerer = Callable[[tuple[str, ...], str], PolicyGenerationResult]


@dataclass(frozen=True)
class CounselContext:
    policies: list[PolicyInput]
    policy_rag_session_ids: tuple[str, ...] = ()
    official_answer: OfficialAnswerer | None = None
    policy_terms_answer: PolicyTermsAnswerer | None = None
