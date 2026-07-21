import asyncio
from typing import cast

from agents import FunctionTool
from agents.tool_context import ToolContext

from app.modules.counsel.agent.tools.official import (
    OfficialGuidanceResult,
    retrieve_official_guidance,
)
from app.modules.counsel.agent.tools.policy_terms import PolicyTermsResult, retrieve_policy_terms
from app.modules.counsel.context import CounselContext
from app.rag.official.answer import RagAnswer
from app.rag.policy.generation import PolicyGenerationResult


def _invoke(tool: FunctionTool, context: CounselContext, arguments: str) -> object:
    tool_context = ToolContext(
        context,
        tool_name=tool.name,
        tool_call_id="call-1",
        tool_arguments=arguments,
    )

    async def invoke() -> object:
        return await tool.on_invoke_tool(tool_context, arguments)

    return asyncio.run(invoke())


def test_official_guidance_returns_the_answer_when_matched() -> None:
    def fake_answerer(_question: str) -> RagAnswer:
        return RagAnswer(
            status="answered",
            answer="고지의무는 계약 전 알릴 의무입니다.",
            citations=(),
            limitations=("일반적인 제도 설명입니다.",),
        )

    context = CounselContext(policies=[], official_answer=fake_answerer)
    result = cast(
        OfficialGuidanceResult,
        _invoke(retrieve_official_guidance, context, '{"query": "고지의무가 뭐야?"}'),
    )

    assert result.matched is True
    assert "고지의무" in result.answer


def test_official_guidance_reports_unmatched_without_guessing() -> None:
    def fake_answerer(_question: str) -> RagAnswer:
        return RagAnswer(status="no_evidence", answer="", citations=(), limitations=())

    context = CounselContext(policies=[], official_answer=fake_answerer)
    result = cast(
        OfficialGuidanceResult,
        _invoke(retrieve_official_guidance, context, '{"query": "존재하지않는제도"}'),
    )

    assert result.matched is False
    assert result.answer == ""


def test_policy_terms_returns_the_answer_when_matched() -> None:
    def fake_answerer(session_ids: tuple[str, ...], _query: str) -> PolicyGenerationResult:
        assert session_ids == ("sess-1",)
        return PolicyGenerationResult(
            answer="증권에 특약 세부 문구가 확인됩니다.",
            evidence_ids=("chunk-1",),
            limitations=(),
            suggestions=(),
            generation="llm",
        )

    context = CounselContext(
        policies=[],
        policy_rag_session_ids=("sess-1",),
        policy_terms_answer=fake_answerer,
    )
    result = cast(
        PolicyTermsResult,
        _invoke(retrieve_policy_terms, context, '{"query": "특약 세부 조건"}'),
    )

    assert result.matched is True
    assert "특약" in result.answer


def test_policy_terms_reports_unmatched_when_generation_falls_back() -> None:
    def fake_answerer(_session_ids: tuple[str, ...], _query: str) -> PolicyGenerationResult:
        return PolicyGenerationResult(
            answer="", evidence_ids=(), limitations=(), suggestions=(), generation="fallback"
        )

    context = CounselContext(
        policies=[],
        policy_rag_session_ids=("sess-1",),
        policy_terms_answer=fake_answerer,
    )
    result = cast(
        PolicyTermsResult,
        _invoke(retrieve_policy_terms, context, '{"query": "지급조건"}'),
    )

    assert result.matched is False


def test_policy_terms_reports_not_indexed_without_session_ids() -> None:
    # No policy_terms_answer override and no session ids: the tool must not
    # attempt a real retrieval call, and must say so rather than guess.
    context = CounselContext(policies=[], policy_rag_session_ids=())
    result = cast(
        PolicyTermsResult,
        _invoke(retrieve_policy_terms, context, '{"query": "특약 조건"}'),
    )

    assert result.matched is False
    assert result.limitations
