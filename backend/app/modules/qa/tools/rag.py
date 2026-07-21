"""Agent SDK tools for the two RAG corpora: official guidance and policy terms."""

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel

from app.modules.qa.context import QaContext
from app.rag.official.answer import answer_official_question
from app.rag.policy.generation import PolicyEvidence, PolicyGenerationResult, generate_policy_answer
from app.rag.policy.retrieval import retrieve_policy_context_by_session_ids


class OfficialGuidanceResult(BaseModel):
    matched: bool
    answer: str
    limitations: list[str]


@function_tool
def retrieve_official_guidance(
    wrapper: RunContextWrapper[QaContext],
    query: str,
) -> OfficialGuidanceResult:
    """공식 문서에 실려 있는 보험 용어·제도 정의를 검색합니다. 이런 질문에 먼저 부르세요:

    - 표준약관(보험업감독업무시행세칙 별표15) — "면책기간이 뭐야?", "감액기간이
      뭐야?", "보상하지 않는 손해가 뭐야?" 같은 정의성 질문
    - 자동차보험 표준상품설명서 — "자차 처리하면 할증돼?", "대인배상/대물배상이
      뭐야?", 자동차보험 특약 구조에 대한 질문
    - 보험업법·금융소비자보호법 — 계약자 권리, 부당승환, 청약철회, 해지 절차 같은
      제도적 질문
    - 찾기 쉬운 생활법령정보(보험계약자) — 일반 소비자 대상 법령 안내

    사용자 증권에 실제로 있는지 여부는 이 도구가 아니라 find_coverages 등으로
    확인하세요. 이 결과는 일반적인 공식 기준이며, 사용자가 실제로 가입한 보험의
    조건과 다를 수 있습니다. 이 도구로 답할 때는 항상 그 사실을 함께 안내하고,
    사용자의 실제 계약 조건인 것처럼 단정하지 마세요. 이 도구가 matched=false를
    반환하면 지어내지 말고 확인 불가라고 답하세요 — 이 corpus에 없다고 해서
    스스로의 지식으로 답을 채우면 안 됩니다.

    (색인된 문서 목록은 data/official-sources/registry.json 참고. 문서가
    추가되면 이 설명도 같이 갱신하세요.)

    Args:
        query: 검색할 보험 용어나 제도에 대한 완전한 질문입니다. 지시어
            없이 그 자체로 뜻이 통해야 합니다.
    """

    answerer = wrapper.context.official_answer or answer_official_question
    result = answerer(query)
    if result.status != "answered":
        return OfficialGuidanceResult(matched=False, answer="", limitations=[])
    return OfficialGuidanceResult(
        matched=True, answer=result.answer, limitations=list(result.limitations)
    )


class PolicyTermsResult(BaseModel):
    matched: bool
    answer: str
    limitations: list[str]


@function_tool
def retrieve_policy_terms(
    wrapper: RunContextWrapper[QaContext],
    query: str,
) -> PolicyTermsResult:
    """사용자가 올린 증권 원문(PDF에서 뽑은 텍스트)에서 세부 문구를 검색합니다.

    find_coverages·calculate_coverage_total 같은 구조화 도구가 담보명·금액은
    이미 정확히 알려주므로, 이 도구는 **그 구조화 추출이 놓친 자유 문구**만
    찾습니다: 특약 세부 조건, 갱신 조건, 증권에 실제로 인쇄된 안내 문구 등.

    증권에는 보통 지급조건·면책·대기기간처럼 **약관 책자에만 있는** 상세
    내용이 없습니다. 그런 질문(예: "면책기간이 뭐야?", "이 수술이 보장
    대상이야?")은 이 도구로 찾으려 하지 말고 retrieve_official_guidance로
    일반 기준을 안내하며 실제 계약과 다를 수 있다고 밝히세요. matched=false가
    돌아오면 지어내지 말고 확인 불가라고 답하세요.

    Args:
        query: 증권 원문에서 찾고 싶은 내용에 대한 완전한 질문입니다. 지시어
            없이 그 자체로 뜻이 통해야 합니다.
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
        matched=True, answer=result.answer, limitations=list(result.limitations)
    )


def _default_policy_terms_answer(
    session_ids: tuple[str, ...], query: str
) -> PolicyGenerationResult:
    hits = retrieve_policy_context_by_session_ids(list(session_ids), query)
    evidence: tuple[PolicyEvidence, ...] = tuple(
        _ChunkEvidence(id=hit.chunk.id, fact=hit.chunk.text) for hit in hits
    )
    return generate_policy_answer(query, evidence)


class _ChunkEvidence(BaseModel):
    id: str
    fact: str
