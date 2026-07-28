import asyncio

from agents.tool_context import ToolContext

from app.modules.qa.context import QaContext
from app.modules.qa.tools.rag import (
    OfficialGuidanceResult,
    PolicyTermsResult,
    retrieve_official_guidance,
    retrieve_policy_terms,
)
from app.rag.official.evidence import (
    OfficialEvidence,
    OfficialEvidenceResult,
)
from app.rag.policy.evidence import (
    PolicyEvidenceResult,
    PolicyTermEvidence,
)


async def _invoke_official_guidance(tool_context: ToolContext[QaContext]) -> object:
    return await retrieve_official_guidance.on_invoke_tool(
        tool_context,
        '{"query":"청약철회 기간은?"}',
    )


async def _invoke_policy_terms(tool_context: ToolContext[QaContext]) -> object:
    return await retrieve_policy_terms.on_invoke_tool(
        tool_context,
        '{"query":"암 보장 시작 조건은?"}',
    )


def test_official_guidance_tool_returns_evidence_instead_of_an_inner_answer() -> None:
    evidence = OfficialEvidence(
        chunk_id="chunk-1",
        excerpt="청약은 보험증권을 받은 날부터 15일 이내 철회할 수 있다.",
        source_id="standard-terms",
        source_title="보험업감독업무시행세칙 별표15 표준약관",
        source_category="standard_clause",
        publisher="금융감독원",
        citation_label="제17조(청약의 철회)",
        page_start=10,
        page_end=10,
    )
    context = QaContext(
        policies=[],
        official_evidence_retriever=lambda _query: OfficialEvidenceResult(
            matched=True,
            evidence=(evidence,),
            limitations=("개별 계약의 확정 조건이 아닙니다.",),
        ),
    )
    tool_context = ToolContext(
        context,
        tool_name="retrieve_official_guidance",
        tool_call_id="call-1",
        tool_arguments='{"query":"청약철회 기간은?"}',
    )

    output = asyncio.run(_invoke_official_guidance(tool_context))

    assert isinstance(output, OfficialGuidanceResult)
    assert output.evidence == (evidence,)
    assert output.evidence[0].citation_label == "제17조(청약의 철회)"
    assert "answer" not in OfficialGuidanceResult.model_fields


def test_policy_terms_tool_returns_evidence_instead_of_an_inner_answer() -> None:
    evidence = PolicyTermEvidence(
        document_ref="document-1",
        excerpt="일반암은 계약일부터 90일이 지난 다음 날부터 보장합니다.",
        content_type="text",
        chunk_index=1,
    )
    context = QaContext(
        policies=[],
        current_question="첫 번째 건강보험의 암 보장 시작 조건은?",
        policy_rag_session_ids=("policy-1",),
        policy_evidence_retriever=lambda _session_ids, _query, _scope: PolicyEvidenceResult(
            has_retrieved_evidence=True,
            evidence=(evidence,),
            limitations=("상세 약관 전체를 대신하지 않습니다.",),
        ),
    )
    tool_context = ToolContext(
        context,
        tool_name="retrieve_policy_terms",
        tool_call_id="call-2",
        tool_arguments='{"query":"암 보장 시작 조건은?"}',
    )

    output = asyncio.run(_invoke_policy_terms(tool_context))

    assert isinstance(output, PolicyTermsResult)
    assert output.has_retrieved_evidence is True
    assert output.supports_exhaustive_answer is False
    assert output.evidence == (evidence,)
    assert output.evidence[0].document_ref == "document-1"
    assert "answer" not in PolicyTermsResult.model_fields


def test_policy_terms_tool_includes_disclosure_fallback_without_another_tool_call() -> None:
    context = QaContext(
        policies=[],
        current_question="암진단비의 모든 면책 사유를 알려줘",
        policy_rag_session_ids=("policy-1",),
        policy_evidence_retriever=lambda _session_ids, _query, _scope: PolicyEvidenceResult(
            has_retrieved_evidence=False,
            requires_disclosure_links=True,
            limitations=("증권 원문만으로 전체 목록을 확정할 수 없습니다.",),
        ),
    )
    tool_context = ToolContext(
        context,
        tool_name="retrieve_policy_terms",
        tool_call_id="call-3",
        tool_arguments='{"query":"암진단비의 면책 사유"}',
    )

    output = asyncio.run(_invoke_policy_terms(tool_context))

    assert isinstance(output, PolicyTermsResult)
    assert output.has_retrieved_evidence is False
    assert output.disclosure_links is not None
    assert output.disclosure_links.insurers == []
