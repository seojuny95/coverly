"""Agent SDK tool for text actually printed on the user's own uploaded policy.

Deliberately narrow: our product only accepts the policy certificate, never
the full terms booklet, so payout conditions/exclusions/waiting periods are
usually not present in what gets indexed here at all. This tool only finds
free-text wording the structured extraction pipeline didn't capture (e.g.
rider details, renewal conditions printed on the certificate itself) — it
does not attempt to answer 지급조건/면책 questions.
"""

from dataclasses import dataclass
from typing import Literal

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel

from app.core.untrusted import strip_injection_markers_by_line
from app.modules.counsel.context import CounselContext
from app.rag.policy.generation import PolicyEvidence, PolicyGenerationResult, generate_policy_answer
from app.rag.policy.retrieval import retrieve_policy_context_by_session_ids


@dataclass
class _ChunkEvidence:
    id: str
    fact: str

    def model_dump(self, *, mode: Literal["json"]) -> dict[str, object]:
        del mode
        return {"id": self.id, "fact": self.fact}


def _default_policy_terms_answer(
    session_ids: tuple[str, ...], query: str
) -> PolicyGenerationResult:
    hits = retrieve_policy_context_by_session_ids(list(session_ids), query)
    evidence: tuple[PolicyEvidence, ...] = tuple(
        _ChunkEvidence(id=hit.chunk.id, fact=hit.chunk.text) for hit in hits
    )
    return generate_policy_answer(query, evidence)


class PolicyTermsResult(BaseModel):
    matched: bool
    answer: str
    limitations: list[str]


@function_tool
def retrieve_policy_terms(
    wrapper: RunContextWrapper[CounselContext],
    query: str,
) -> PolicyTermsResult:
    """사용자가 올린 증권 원문에서 구조화 추출이 놓친 세부 문구를 검색합니다.

    증권에는 보통 지급조건·면책·대기기간처럼 약관 책자에만 있는 상세 내용이
    없습니다. 그런 질문은 이 도구로 확인하려 하지 말고 retrieve_official_guidance로
    일반 기준을 안내하며 실제 계약과 다를 수 있다고 밝히세요. 이 도구는 증권에
    실제로 인쇄된 문구(특약 세부, 갱신 조건 등)를 찾을 때만 사용하세요.

    Args:
        query: 증권 원문에서 찾고 싶은 내용에 대한 완전한 질문입니다.
    """

    context = wrapper.context
    if context.policy_terms_answer is not None:
        result = context.policy_terms_answer(context.policy_rag_session_ids, query)
    elif not context.policy_rag_session_ids:
        return PolicyTermsResult(
            matched=False,
            answer="",
            limitations=["증권 원문이 아직 색인되지 않았거나 업로드되지 않았습니다."],
        )
    else:
        result = _default_policy_terms_answer(context.policy_rag_session_ids, query)

    if result.generation == "fallback":
        return PolicyTermsResult(matched=False, answer="", limitations=[])
    return PolicyTermsResult(
        matched=True,
        answer=strip_injection_markers_by_line(result.answer),
        limitations=list(result.limitations),
    )
