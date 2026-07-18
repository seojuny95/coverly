"""Agent SDK tools for official and uploaded-policy retrieval."""

from agents import RunContextWrapper, function_tool

from app.modules.evidence.catalog import with_session_evidence
from app.modules.qa.agent.contracts import GroundedToolAnswer, QaAgentDependencies
from app.modules.qa.citations import citation_from_evidence
from app.modules.qa.contracts import AnswerSection
from app.modules.qa.response_support import question_suggestions, with_demographics
from app.modules.qa.schemas import AnswerCitation, PortfolioQuestionResponse
from app.rag.official.answer import RagAnswer, RagCitation, answer_official_question
from app.rag.policy import (
    generate_policy_answer,
    retrieve_policy_context_by_session_ids,
)


@function_tool
def retrieve_official_guidance(
    wrapper: RunContextWrapper[QaAgentDependencies],
    query: str,
) -> GroundedToolAnswer:
    """Retrieve stable insurance terminology, standard clauses, and official guidance.

    Args:
        query: The complete insurance question to retrieve from official sources.
    """

    dependencies = wrapper.context
    answerer = dependencies.official_answer or answer_official_question
    try:
        result = answerer(query)
    except Exception:
        return dependencies.unmatched("official_rag", "Official RAG retrieval failed.")
    if result.status != "answered":
        return dependencies.unmatched("official_rag", "Official RAG had no grounded answer.")

    response = _official_response(result)
    return dependencies.register(
        "official_rag",
        with_demographics(response, dependencies.context.insured),
    )


@function_tool
def retrieve_policy_terms(
    wrapper: RunContextWrapper[QaAgentDependencies],
    query: str,
) -> GroundedToolAnswer:
    """Retrieve uploaded policy text for conditions, exclusions, waiting periods, or wording.

    Args:
        query: The complete question to search in the user's uploaded policy sessions.
    """

    dependencies = wrapper.context
    context = dependencies.context
    if not context.policy_rag_session_ids:
        return dependencies.unmatched(
            "policy_terms",
            "No uploaded policy-text session exists.",
        )

    try:
        hits = retrieve_policy_context_by_session_ids(
            list(context.policy_rag_session_ids),
            query,
        )
    except Exception:
        return dependencies.unmatched("policy_terms", "Uploaded policy retrieval failed.")
    if not hits:
        return dependencies.unmatched("policy_terms", "No uploaded policy text matched.")

    catalog = with_session_evidence(context.catalog, hits)
    evidence = tuple(item for item in catalog.items if item.id.startswith("session:"))
    result = generate_policy_answer(query, evidence, complete=dependencies.complete)
    if result.generation == "fallback":
        return dependencies.unmatched("policy_terms", "Policy evidence was insufficient.")

    selected_evidence = tuple(
        catalog.by_id[evidence_id]
        for evidence_id in result.evidence_ids
        if evidence_id in catalog.by_id
    )
    section = AnswerSection(
        title="업로드 증권 근거",
        content=result.answer,
        basis="confirmed_fact",
    )
    response = PortfolioQuestionResponse(
        status="answered",
        answer=f"가입하신 상품의 원문에서 확인한 내용이에요.\n\n{result.answer.strip()}",
        sections=[section],
        citations=[citation_from_evidence(item) for item in selected_evidence],
        limitations=list(result.limitations),
        suggestions=list(result.suggestions),
        generation="llm",
    )
    return dependencies.register(
        "policy_terms",
        with_demographics(response, context.insured),
        evidence=selected_evidence,
    )


def _official_response(result: RagAnswer) -> PortfolioQuestionResponse:
    section = AnswerSection(
        title="공식자료 기준 일반 안내",
        content=result.answer,
        basis="general_guidance",
    )
    return PortfolioQuestionResponse(
        status="answered",
        answer=f"공식자료에서 확인한 일반 안내예요.\n\n{result.answer.strip()}",
        sections=[section],
        citations=[_official_citation(citation) for citation in result.citations],
        limitations=list(result.limitations),
        suggestions=question_suggestions(
            "이 내용이 내 증권에도 들어 있어?", "내 담보 지급 조건은 뭐야?"
        ),
        generation="llm",
    )


def _official_citation(citation: RagCitation) -> AnswerCitation:
    return AnswerCitation(
        evidence_id=citation.chunk_id,
        policy_id=None,
        insurer=None,
        product_name=None,
        source_id=citation.source_id,
        source_title=citation.source_title,
        source_category=citation.source_category,
        source_url=citation.source_url,
        source_page=citation.page_start,
        source_version=citation.version_label,
    )
