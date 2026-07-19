"""Validation and grounding for final QA agent responses."""

from app.modules.consultation.contracts import ConsultationEvidence
from app.modules.evidence.catalog import (
    valid_evidence_ids,
)
from app.modules.qa.agent.contracts import (
    AgentCounselorDraft,
    QaAgentDependencies,
    QaAgentUnavailable,
    RegisteredToolResult,
)
from app.modules.qa.agent.grounding import (
    NUMERIC_CLAIM,
    numeric_claims_are_grounded,
    numeric_claims_grounded_in_sources,
)
from app.modules.qa.agent.input_guardrail import (
    requires_fresh_official_source,
    requires_uploaded_policy_terms,
)
from app.modules.qa.agent.selection import select_tool_result
from app.modules.qa.citations import citation_from_evidence
from app.modules.qa.context import QaContext
from app.modules.qa.response_support import (
    contextual_suggestions,
    out_of_scope_response,
    standard_limitations,
    with_demographics,
)
from app.modules.qa.schemas import AnswerCitation, PortfolioQuestionResponse

_DEGRADED_SYNTHESIS_NOTE = (
    "확인된 개별 항목의 답변만 그대로 정리했고, 근거 없는 종합 수치는 포함하지 않았습니다."
)


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
            return _missing_required_policy_terms_response(context, dependencies)
        return _validated_insufficient_evidence_response(context, draft, dependencies)
    if draft.answer_mode == "general_guidance":
        if requires_uploaded_policy_terms(dependencies):
            return _missing_required_policy_terms_response(context, dependencies)
        if requires_fresh_official_source(dependencies):
            return _missing_required_web_response(context)
        return _validated_general_guidance_response(context, draft)

    matched_results = list(dependencies.tool_results.values())
    is_synthesis = (
        draft.answer_mode == "tool_grounded"
        and draft.selected_result_id is None
        and len(matched_results) > 1
        and not requires_fresh_official_source(dependencies)
        and not requires_uploaded_policy_terms(dependencies)
    )
    if is_synthesis:
        return _validated_synthesis_response(context, draft, matched_results, dependencies)

    selected = select_tool_result(dependencies, draft.selected_result_id)
    if (
        selected is not None
        and requires_uploaded_policy_terms(dependencies)
        and selected.kind in {"official_rag", "web"}
    ):
        return _missing_required_policy_terms_response(context, dependencies)
    if selected is None and requires_uploaded_policy_terms(dependencies):
        return _missing_required_policy_terms_response(context, dependencies)
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


def _validated_synthesis_response(
    context: QaContext,
    draft: AgentCounselorDraft,
    results: list[RegisteredToolResult],
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse:
    authoritative = [item.response.answer for item in results]
    union_evidence = tuple(ev for item in results for ev in item.evidence)
    answer = draft.answer.strip()

    citations = _synthesis_citations(draft, union_evidence, results)

    # An answered synthesis must rest on real grounding: either an evidence
    # citation resolved from the participating results' own union, or a numeric
    # claim that Task 4a verified against those results. Otherwise the model has
    # only produced ungrounded prose (or a fabricated number), so we degrade to
    # the confirmed individual answers instead of dressing prose up as grounded.
    numbers_grounded = numeric_claims_grounded_in_sources(answer, authoritative, union_evidence)
    has_union_citation = _has_union_evidence_citation(draft, union_evidence)
    has_grounded_number = numbers_grounded and NUMERIC_CLAIM.search(answer) is not None
    if not numbers_grounded or not (has_union_citation or has_grounded_number):
        return _degraded_synthesis_response(context, draft, results, dependencies)

    decision = dependencies.input_decision
    if decision is not None and decision.scope == "mixed":
        answer = f"{answer}\n\n보험 상담 범위 밖의 내용은 여기서 답하기 어려워요."

    limitations = list(
        dict.fromkeys(
            [lim for item in results for lim in item.response.limitations]
            + list(standard_limitations(context.facts))
        )
    )
    return with_demographics(
        PortfolioQuestionResponse(
            status="answered",
            answer=answer,
            citations=citations,
            limitations=limitations,
            suggestions=contextual_suggestions(context),
            generation="llm",
        ),
        context.insured,
    )


def _degraded_synthesis_response(
    context: QaContext,
    draft: AgentCounselorDraft,
    results: list[RegisteredToolResult],
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse:
    """Fall back to the confirmed tool answers verbatim, dropping model prose.

    The model's own wording is discarded (it carried an ungrounded number or no
    grounding at all). Each participating result's `response.answer` is already
    grounded tool output, so surfacing them in order stays honest without any
    scoring, ranking, or synthesized number.
    """

    confirmed = [
        item
        for item in results
        if item.response.status == "answered" and item.response.answer.strip()
    ]
    if not confirmed:
        return _missing_grounded_synthesis_response(context)

    answer = "\n\n".join(item.response.answer.strip() for item in confirmed)
    decision = dependencies.input_decision
    if decision is not None and decision.scope == "mixed":
        answer = f"{answer}\n\n보험 상담 범위 밖의 내용은 여기서 답하기 어려워요."

    union_evidence = tuple(ev for item in confirmed for ev in item.evidence)
    citations = _synthesis_citations(draft, union_evidence, confirmed)
    limitations = list(
        dict.fromkeys(
            [lim for item in confirmed for lim in item.response.limitations]
            + [_DEGRADED_SYNTHESIS_NOTE]
            + list(standard_limitations(context.facts))
        )
    )
    return with_demographics(
        PortfolioQuestionResponse(
            status="answered",
            answer=answer,
            citations=citations,
            limitations=limitations,
            suggestions=contextual_suggestions(context),
            generation="llm",
        ),
        context.insured,
    )


def _missing_grounded_synthesis_response(context: QaContext) -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="no_data",
        answer="질문에 필요한 근거를 도구에서 확인하지 못했습니다.",
        citations=[],
        limitations=["확인된 근거가 없어 종합 답변을 만들지 않았습니다."],
        suggestions=[],
        demographics=context.insured,
    )


def _has_union_evidence_citation(
    draft: AgentCounselorDraft,
    union_evidence: tuple[ConsultationEvidence, ...],
) -> bool:
    union_ids = {item.id for item in union_evidence}
    return any(eid in union_ids for eid in draft.evidence_ids)


def _synthesis_citations(
    draft: AgentCounselorDraft,
    union_evidence: tuple[ConsultationEvidence, ...],
    results: list[RegisteredToolResult],
) -> list[AnswerCitation]:
    by_id = {item.id: item for item in union_evidence}
    evidence_citations = [
        citation_from_evidence(by_id[eid])
        for eid in dict.fromkeys(draft.evidence_ids)
        if eid in by_id
    ]
    native_citations = [citation for item in results for citation in item.response.citations]

    seen: set[str] = set()
    deduped: list[AnswerCitation] = []
    for citation in [*evidence_citations, *native_citations]:
        key = citation.model_dump_json()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped[:3]


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


def _missing_required_policy_terms_response(
    context: QaContext,
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse:
    reason = _policy_terms_failure_reason(dependencies)
    if reason is not None and "session" in reason:
        answer = (
            "아직 약관 원문을 확인할 준비가 되지 않았어요. 약관을 읽는 중이거나 "
            "아직 업로드되지 않았을 수 있어요."
        )
    else:
        answer = (
            "가입하신 보험의 정확한 조건은 업로드된 약관 원문에서 확인해야 해요. "
            "현재 원문 근거에서는 질문하신 조건을 확인하지 못했습니다."
        )
    return PortfolioQuestionResponse(
        status="no_data",
        answer=answer,
        citations=[],
        limitations=["일반 공식자료를 가입한 보험의 실제 계약 조건으로 대신하지 않았습니다."],
        suggestions=[],
        demographics=context.insured,
    )


def _policy_terms_failure_reason(dependencies: QaAgentDependencies) -> str | None:
    for failure in dependencies.tool_failures:
        if failure.kind == "policy_terms":
            return failure.reason
    return None
