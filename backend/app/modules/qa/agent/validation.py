"""Validation and grounding for final QA agent responses."""

from app.modules.evidence.catalog import (
    citation_from_evidence,
    valid_evidence_ids,
)
from app.modules.qa.agent.contracts import (
    AgentCounselorDraft,
    QaAgentDependencies,
    QaAgentUnavailable,
)
from app.modules.qa.agent.grounding import (
    NUMERIC_CLAIM,
    numeric_claims_are_grounded,
)
from app.modules.qa.agent.input_guardrail import (
    requires_fresh_official_source,
    requires_uploaded_policy_terms,
)
from app.modules.qa.agent.selection import select_tool_result
from app.modules.qa.context import QaContext
from app.modules.qa.response_support import (
    contextual_suggestions,
    out_of_scope_response,
    standard_limitations,
    with_demographics,
)
from app.modules.qa.schemas import PortfolioQuestionResponse


def validated_agent_response(
    context: QaContext,
    draft: AgentCounselorDraft,
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse:
    if (
        draft.answer_mode == "insufficient_evidence"
        and draft.selected_result_id is not None
        and draft.selected_result_id in dependencies.tool_results
    ):
        draft = draft.model_copy(update={"answer_mode": "tool_grounded"})

    decision = dependencies.input_decision
    if (
        decision is not None
        and decision.scope == "mixed"
        and draft.answer_mode not in {"tool_grounded", "insufficient_evidence"}
    ):
        raise QaAgentUnavailable("Mixed-scope insurance question requires a grounded tool result")
    if draft.answer_mode == "general_guidance" and dependencies.tool_results:
        draft = draft.model_copy(update={"answer_mode": "tool_grounded"})
    if draft.answer_mode == "out_of_scope":
        if decision is not None and decision.scope != "out_of_scope":
            raise QaAgentUnavailable("Agent answer mode conflicts with the input scope")
        return out_of_scope_response(context)
    if draft.answer_mode == "insufficient_evidence":
        if requires_uploaded_policy_terms(dependencies):
            return _missing_required_policy_terms_response(context)
        return _validated_insufficient_evidence_response(context, draft, dependencies)
    if draft.answer_mode == "general_guidance":
        if requires_uploaded_policy_terms(dependencies):
            return _missing_required_policy_terms_response(context)
        if requires_fresh_official_source(dependencies):
            return _missing_required_web_response(context)
        return _validated_general_guidance_response(context, draft)

    selected = select_tool_result(dependencies, draft.selected_result_id)
    if (
        selected is not None
        and requires_uploaded_policy_terms(dependencies)
        and selected.kind in {"official_rag", "web"}
    ):
        return _missing_required_policy_terms_response(context)
    if selected is None and requires_uploaded_policy_terms(dependencies):
        return _missing_required_policy_terms_response(context)
    if selected is None and requires_fresh_official_source(dependencies):
        return _missing_required_web_response(context)
    if selected is None:
        raise QaAgentUnavailable("Agent did not select an unambiguous grounded tool result")

    response = selected.response
    answer = response.answer if response.status != "answered" else draft.answer.strip()
    if decision is not None and decision.scope == "mixed":
        answer = f"{answer}\n\n보험 상담 범위 밖의 내용은 여기서 답하기 어려워요."
    citations = response.citations
    grounded_evidence = selected.evidence
    if selected.kind == "consultation":
        evidence_ids = valid_evidence_ids(draft.evidence_ids, context.catalog)
        available_ids = {item.id for item in grounded_evidence}
        if evidence_ids is None or any(item_id not in available_ids for item_id in evidence_ids):
            raise QaAgentUnavailable("Agent consultation answer cited invalid evidence")
        grounded_evidence = tuple(context.catalog.by_id[item_id] for item_id in evidence_ids)
        citations = [citation_from_evidence(item) for item in grounded_evidence[:3]]

    if not numeric_claims_are_grounded(answer, response.answer, grounded_evidence):
        if selected.kind == "consultation":
            raise QaAgentUnavailable("Agent consultation answer introduced an unsupported number")
        answer = response.answer
        citations = response.citations

    if selected.kind == "web":
        return response.model_copy(
            update={"answer": answer, "generation": "llm", "demographics": context.insured}
        )

    limitations = list(dict.fromkeys([*response.limitations, *standard_limitations(context.facts)]))
    return with_demographics(
        response.model_copy(
            update={
                "answer": answer,
                "citations": citations,
                "limitations": limitations,
                "suggestions": response.suggestions or contextual_suggestions(context),
                "generation": "llm",
            }
        ),
        context.insured,
    )


def _validated_general_guidance_response(
    context: QaContext,
    draft: AgentCounselorDraft,
) -> PortfolioQuestionResponse:
    answer = draft.answer.strip()
    if draft.selected_result_id is not None or draft.evidence_ids:
        raise QaAgentUnavailable("General guidance must not cite tool results or evidence")
    if NUMERIC_CLAIM.search(answer):
        raise QaAgentUnavailable("General guidance introduced a numeric portfolio claim")

    return with_demographics(
        PortfolioQuestionResponse(
            status="answered",
            answer=answer,
            citations=[],
            limitations=["업로드 증권의 구체 사실을 조회하지 않은 일반 안내입니다."],
            suggestions=contextual_suggestions(context),
            generation="llm",
        ),
        context.insured,
    )


def _validated_insufficient_evidence_response(
    context: QaContext,
    draft: AgentCounselorDraft,
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse:
    if draft.selected_result_id is not None or draft.evidence_ids:
        raise QaAgentUnavailable("Insufficient-evidence output must not cite successful results")
    if not dependencies.tool_failures:
        raise QaAgentUnavailable("Insufficient-evidence output requires a failed tool lookup")
    if dependencies.tool_results:
        raise QaAgentUnavailable("Agent ignored an available grounded tool result")

    answer = draft.answer.strip()
    if dependencies.input_decision is not None and dependencies.input_decision.scope == "mixed":
        answer = f"{answer}\n\n보험 상담 범위 밖의 내용은 여기서 답하기 어려워요."
    return with_demographics(
        PortfolioQuestionResponse(
            status="no_data",
            answer=answer,
            citations=[],
            limitations=["질문에 필요한 근거를 도구에서 확인하지 못했습니다."],
            suggestions=[],
            generation="llm",
        ),
        context.insured,
    )


def _missing_required_web_response(context: QaContext) -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="no_data",
        answer=(
            "최신 공식 정보를 확인하지 못했어요. 현재 안내나 최근 변경은 허용된 "
            "공식 웹사이트 검색 근거가 있어야 답할 수 있어요."
        ),
        citations=[],
        limitations=["공식 웹검색이 완료되지 않아 기존 자료로 대신 답하지 않았습니다."],
        suggestions=[],
        demographics=context.insured,
    )


def _missing_required_policy_terms_response(context: QaContext) -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="no_data",
        answer=(
            "가입하신 보험의 정확한 조건은 업로드된 약관 원문에서 확인해야 해요. "
            "현재 원문 근거에서는 질문하신 조건을 확인하지 못했습니다."
        ),
        citations=[],
        limitations=["일반 공식자료를 가입한 보험의 실제 계약 조건으로 대신하지 않았습니다."],
        suggestions=[],
        demographics=context.insured,
    )
