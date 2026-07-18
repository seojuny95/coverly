"""Validation and guardrails for final QA agent responses."""

import re

from app.modules.evidence.catalog import (
    citation_from_evidence,
    is_safe_analysis_text,
    valid_evidence_ids,
)
from app.modules.qa.agent_contracts import (
    AgentCounselorDraft,
    QaAgentDependencies,
    QaAgentUnavailable,
    RegisteredToolResult,
)
from app.modules.qa.context import QaContext
from app.modules.qa.contracts import ConsultationEvidence
from app.modules.qa.resolvers import contextual_suggestions, standard_limitations, with_demographics
from app.modules.qa.schemas import PortfolioQuestionResponse


def validated_agent_response(
    context: QaContext,
    draft: AgentCounselorDraft,
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse:
    if draft.answer_mode == "general_guidance" and requires_official_web(context.question):
        return _missing_required_web_response(context)
    if draft.answer_mode == "general_guidance":
        return _validated_general_guidance_response(context, draft)

    selected = _select_tool_result(context, draft, dependencies)
    if selected is None and requires_official_web(context.question):
        return _missing_required_web_response(context)
    if selected is None:
        raise QaAgentUnavailable("Agent did not select an unambiguous grounded tool result")

    response = selected.response
    answer = response.answer if response.status != "answered" else draft.answer.strip()
    allow_official_claims = selected.kind in {"grounded", "web"}
    if not is_safe_analysis_text(answer, allow_official_claims=allow_official_claims):
        if selected.kind == "consultation":
            raise QaAgentUnavailable("Agent consultation answer failed safety validation")
        answer = response.answer

    citations = response.citations
    grounded_evidence = selected.evidence
    if selected.kind == "consultation":
        evidence_ids = valid_evidence_ids(draft.evidence_ids, context.catalog)
        available_ids = {item.id for item in grounded_evidence}
        if evidence_ids is None or any(item_id not in available_ids for item_id in evidence_ids):
            raise QaAgentUnavailable("Agent consultation answer cited invalid evidence")
        grounded_evidence = tuple(context.catalog.by_id[item_id] for item_id in evidence_ids)
        citation_evidence = _answer_relevant_evidence(answer, grounded_evidence)
        citations = [citation_from_evidence(item) for item in citation_evidence]

    if not _numeric_claims_are_grounded(
        answer,
        response.answer,
        grounded_evidence,
    ):
        if selected.kind == "consultation":
            raise QaAgentUnavailable("Agent consultation answer introduced an unsupported number")
        answer = response.answer
        citations = response.citations

    if selected.kind == "web":
        return response.model_copy(
            update={
                "answer": answer,
                "generation": "llm",
                "demographics": context.insured,
            }
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


def requires_official_web(question: str) -> bool:
    """Return whether this turn must be grounded in a fresh official web search."""

    return any(term in question for term in _LATEST_INFORMATION_TERMS) and any(
        term in question for term in _OFFICIAL_WEB_TOPIC_TERMS
    )


def required_first_tool(context: QaContext) -> str | None:
    if requires_official_web(context.question):
        return "search_official_web"
    return None


def _answer_relevant_evidence(
    answer: str,
    evidence: tuple[ConsultationEvidence, ...],
) -> tuple[ConsultationEvidence, ...]:
    relevant: list[ConsultationEvidence] = []
    for item in evidence:
        terms = (item.coverage_name, item.insurer, item.product_name)
        if any(term and term in answer for term in terms):
            relevant.append(item)
    if relevant:
        return tuple(relevant[:3])
    return evidence[:1]


def _select_tool_result(
    context: QaContext,
    draft: AgentCounselorDraft,
    dependencies: QaAgentDependencies,
) -> RegisteredToolResult | None:
    selected = (
        dependencies.tool_results.get(draft.selected_result_id)
        if draft.selected_result_id is not None
        else None
    )
    if requires_official_web(context.question):
        if selected is not None and selected.kind == "web":
            return selected
        web_results = [item for item in dependencies.tool_results.values() if item.kind == "web"]
        return web_results[0] if len(web_results) == 1 else None

    if selected is not None:
        return selected

    results = list(dependencies.tool_results.values())
    if len(results) == 1:
        return results[0]
    if results and all(item.response == results[0].response for item in results[1:]):
        return results[0]
    return None


_NUMERIC_CLAIM = re.compile(r"\d[\d,]*\s*(?:(?:억|만|천)\s*)?원|\d[\d,]*\s*(?:세|건|종|개)")
_LATEST_INFORMATION_TERMS = ("최신", "최근", "요즘", "개정", "변경된", "변경 사항")
_OFFICIAL_WEB_TOPIC_TERMS = (
    "보험업법",
    "법령",
    "표준약관",
    "공개 약관",
    "보험사",
    "금융위원회",
    "금융감독원",
    "보험 용어",
    "공식 안내",
)


def _validated_general_guidance_response(
    context: QaContext,
    draft: AgentCounselorDraft,
) -> PortfolioQuestionResponse:
    answer = draft.answer.strip()
    if draft.selected_result_id is not None or draft.evidence_ids:
        raise QaAgentUnavailable("General guidance must not cite tool results or evidence")
    if not is_safe_analysis_text(answer, allow_official_claims=False):
        raise QaAgentUnavailable("General guidance failed safety validation")
    if _NUMERIC_CLAIM.search(answer):
        raise QaAgentUnavailable("General guidance introduced a numeric portfolio claim")
    if _mentions_uploaded_policy_identity(answer, context):
        raise QaAgentUnavailable("General guidance mentioned uploaded-policy identities")

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


def _mentions_uploaded_policy_identity(answer: str, context: QaContext) -> bool:
    identities: set[str] = set()
    for policy in context.policies:
        identities.update(
            value
            for value in (
                policy.id,
                policy.기본정보.보험사,
                policy.기본정보.상품명,
                *(coverage.담보명 for coverage in policy.보장목록),
            )
            if value and len(value.strip()) >= 2
        )
    return any(identity in answer for identity in identities)


def _numeric_claims_are_grounded(
    answer: str,
    authoritative_answer: str,
    evidence: tuple[ConsultationEvidence, ...],
) -> bool:
    claims = {_normalize_numeric_claim(item) for item in _NUMERIC_CLAIM.findall(answer)}
    if not claims:
        return True

    source = "\n".join([authoritative_answer, *(item.fact for item in evidence)])
    grounded = {_normalize_numeric_claim(item) for item in _NUMERIC_CLAIM.findall(source)}
    return claims <= grounded


def _normalize_numeric_claim(value: str) -> str:
    return re.sub(r"[\s,]", "", value)


def _missing_required_web_response(context: QaContext) -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="no_data",
        answer=(
            "최신 공식 정보를 확인하지 못했어요. 최신·최근 변경 질문은 허용된 "
            "공식 웹사이트 검색 근거가 있어야 답할 수 있어요."
        ),
        citations=[],
        limitations=["공식 웹검색이 완료되지 않아 기존 자료로 대신 답하지 않았습니다."],
        suggestions=[],
        demographics=context.insured,
    )
