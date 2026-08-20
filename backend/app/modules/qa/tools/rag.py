"""Agent SDK tools for the two RAG corpora: official guidance and policy terms."""

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel

from app.modules.qa.context import QaContext
from app.modules.qa.facts import disclosure as disclosure_facts
from app.observability.agent_tracing import agent_tool_trace_context
from app.rag.official.evidence import OfficialEvidence, search_official_evidence
from app.rag.policy.evidence import PolicyTermEvidence, search_policy_evidence


class OfficialGuidanceResult(BaseModel):
    matched: bool
    evidence: tuple[OfficialEvidence, ...]
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
    확인하세요. 이 도구는 완성된 답변이 아니라 evidence에 검색 발췌문과 출처를
    반환합니다. 질문에 필요한 근거만 골라 직접 설명하고 citation_label과
    source_title로 출처를 밝혀 주세요. limitations도 답변 경계에 반영하세요.

    이 결과는 일반적인 공식 기준이며, 사용자가 실제로 가입한 보험의 조건과 다를
    수 있습니다. 사용자의 실제 계약 조건인 것처럼 단정하지 마세요.
    matched=false면 지어내지 말고 확인 불가라고 답하세요. corpus에 없다고 해서
    모델의 일반 지식으로 답을 채우면 안 됩니다.

    (색인된 문서 목록은 data/official-sources/registry.json 참고. 문서가
    추가되면 이 설명도 같이 갱신하세요.)

    Args:
        query: 검색할 보험 용어나 제도에 대한 완전한 질문입니다. 지시어
            없이 그 자체로 뜻이 통해야 합니다.
    """

    retriever = wrapper.context.official_evidence_retriever or search_official_evidence
    with agent_tool_trace_context():
        result = retriever(query)
    return OfficialGuidanceResult(
        matched=result.matched,
        evidence=result.evidence,
        limitations=list(result.limitations),
    )


class PolicyTermsResult(BaseModel):
    has_retrieved_evidence: bool
    supports_exhaustive_answer: bool
    evidence: tuple[PolicyTermEvidence, ...]
    limitations: list[str]
    disclosure_links: disclosure_facts.DisclosureLinksResult | None = None


@function_tool
def retrieve_policy_terms(
    wrapper: RunContextWrapper[QaContext],
    query: str,
) -> PolicyTermsResult:
    """사용자가 올린 증권 원문(PDF에서 뽑은 텍스트)에서 세부 문구를 검색합니다.

    find_coverages·calculate_coverage_total 같은 구조화 도구가 담보명·금액은
    이미 정확히 알려주므로, 이 도구는 **그 구조화 추출이 놓친 자유 문구**만
    찾습니다: 특약 세부 조건, 갱신 조건, 증권에 실제로 인쇄된 안내 문구 등.

    이 도구는 완성된 답변이 아니라 evidence에 증권 원문 발췌문과 문서 참조값을
    반환합니다. has_retrieved_evidence는 검색 후보가 있다는 뜻이며 질문에 충분한
    답이 있다는 보장은 아닙니다. 질문과 직접 관련된 발췌문만 골라 설명하고, 서로
    다른 document_ref의 조건을 섞지 마세요. limitations에 있는 한계를 답변에
    반영하세요.

    supports_exhaustive_answer=false는 검색 발췌문만으로 "모든", "전부",
    "빠짐없이" 같은 전체 목록을 보장할 수 없다는 뜻입니다. 검색 근거가 부족하면
    disclosure_links에 검증된 공식 약관 확인 경로가 함께 반환됩니다.

    증권에는 보통 지급조건·면책·대기기간처럼 **약관 책자에만 있는** 상세
    내용이 없습니다. 그런 질문(예: "면책기간이 뭐야?", "이 수술이 보장
    대상이야?")은 이 도구로 찾으려 하지 말고 retrieve_official_guidance로
    일반 기준을 안내하며 실제 계약과 다를 수 있다고 밝히세요.
    has_retrieved_evidence=false이거나 검색 발췌문만으로 질문에 충분히 답할 수
    없으면 지어내지 말고 disclosure_links의 공식 약관 확인 경로를 안내하세요.

    Args:
        query: 증권 원문에서 찾고 싶은 내용에 대한 완전한 질문입니다. 지시어
            없이 그 자체로 뜻이 통해야 합니다.
    """

    context = wrapper.context
    with agent_tool_trace_context():
        if context.policy_evidence_retriever is not None:
            result = context.policy_evidence_retriever(
                context.policy_rag_session_ids,
                query,
                context.current_question,
            )
        else:
            result = search_policy_evidence(
                context.policy_rag_session_ids,
                query,
                scope_question=context.current_question,
            )
    return PolicyTermsResult(
        has_retrieved_evidence=result.has_retrieved_evidence,
        supports_exhaustive_answer=result.supports_exhaustive_answer,
        evidence=result.evidence,
        limitations=list(result.limitations),
        disclosure_links=(
            disclosure_facts.get_disclosure_link_facts(context.policies)
            if result.requires_disclosure_links
            else None
        ),
    )
