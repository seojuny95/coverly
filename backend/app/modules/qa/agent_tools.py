"""Function tools and evidence selection for the grounded QA agent."""

from urllib.parse import urlparse

from agents import RunContextWrapper, function_tool

from app.modules.evidence.catalog import citation_from_evidence
from app.modules.qa.agent_contracts import GroundedToolAnswer, QaAgentDependencies
from app.modules.qa.agent_evidence import (
    consultation_evidence,
    portfolio_snapshot_evidence,
    response_evidence,
)
from app.modules.qa.context import QaContext, context_with_question
from app.modules.qa.resolvers import (
    contextual_suggestions,
    resolve_precomputed_answer,
    standard_limitations,
    with_demographics,
)
from app.modules.qa.schemas import AnswerCitation, PortfolioQuestionResponse
from app.modules.qa.web_search import (
    SearchPurpose,
    WebSearchResult,
    sanitize_search_query,
    search_allowed_domains,
)
from app.rag.official.answer import answer_official_question
from app.rag.policy import generate_policy_answer, retrieve_policy_context


@function_tool
def list_policies(wrapper: RunContextWrapper[QaAgentDependencies]) -> GroundedToolAnswer:
    """List all uploaded policies across every insurance classification."""

    dependencies = wrapper.context
    context = context_with_question(dependencies.context, "가입한 보험 목록 알려줘")
    response = _resolve_precomputed_for_context(dependencies, context)
    if response is None:
        return GroundedToolAnswer(matched=False, reason="No uploaded policy list was available.")
    return dependencies.register(
        "policies",
        with_demographics(response, context.insured),
        evidence=response_evidence(context, response),
    )


@function_tool
def find_coverages(
    wrapper: RunContextWrapper[QaAgentDependencies],
    query: str,
) -> GroundedToolAnswer:
    """Find uploaded-policy coverages related to the user's question."""

    dependencies = wrapper.context
    context = dependencies.context
    response = _resolve_precomputed_for_context(dependencies, context)
    if response is not None and response.status == "answered":
        return dependencies.register(
            "coverage_lookup",
            with_demographics(response, context.insured),
            evidence=response_evidence(context, response),
        )

    context = context_with_question(dependencies.context, query or dependencies.context.question)
    evidence = consultation_evidence(context)
    if not evidence:
        return GroundedToolAnswer(
            matched=False,
            reason="No uploaded-policy coverage evidence matched the query.",
        )
    answer = "질문과 관련해 업로드 증권에서 확인된 근거예요.\n\n" + "\n".join(
        f"- {item.fact}" for item in evidence
    )
    grounded = PortfolioQuestionResponse(
        status="answered",
        answer=answer,
        citations=[citation_from_evidence(item) for item in evidence],
        limitations=standard_limitations(context.facts),
        suggestions=contextual_suggestions(context),
    )
    return dependencies.register(
        "coverage_lookup",
        with_demographics(grounded, context.insured),
        evidence=evidence,
    )


@function_tool
def calculate_coverage_total(
    wrapper: RunContextWrapper[QaAgentDependencies],
    coverage_query: str,
) -> GroundedToolAnswer:
    """Calculate confirmed fixed-benefit amount totals for a requested coverage."""

    dependencies = wrapper.context
    question = (
        f"{coverage_query} 가입금액 합계는 얼마야?"
        if coverage_query.strip()
        else dependencies.context.question
    )
    context = context_with_question(dependencies.context, question)
    response = _resolve_precomputed_for_context(dependencies, context)
    if response is None:
        return GroundedToolAnswer(matched=False, reason="No calculable coverage total matched.")
    return dependencies.register(
        "coverage_total",
        with_demographics(response, context.insured),
        evidence=response_evidence(context, response),
    )


@function_tool
def find_overlapping_coverages(
    wrapper: RunContextWrapper[QaAgentDependencies],
) -> GroundedToolAnswer:
    """Find duplicate fixed-benefit coverages or repeated actual-loss coverages."""

    dependencies = wrapper.context
    context = context_with_question(dependencies.context, "겹치는 보장이 있는지 확인해줘")
    evidence = consultation_evidence(context)
    if not evidence:
        return GroundedToolAnswer(
            matched=False,
            reason="No overlap evidence was available.",
        )
    answer = "업로드 증권 전체에서 중복 여부를 확인한 근거예요.\n\n" + "\n".join(
        f"- {item.fact}" for item in evidence
    )
    response = PortfolioQuestionResponse(
        status="answered",
        answer=answer,
        citations=[citation_from_evidence(item) for item in evidence],
        limitations=standard_limitations(context.facts),
        suggestions=contextual_suggestions(context),
    )
    return dependencies.register(
        "coverage_overlap",
        with_demographics(response, context.insured),
        evidence=evidence,
    )


@function_tool
def get_claim_channels(
    wrapper: RunContextWrapper[QaAgentDependencies],
    claim_query: str,
) -> GroundedToolAnswer:
    """Return claim-channel guidance for the relevant held policies."""

    dependencies = wrapper.context
    context = context_with_question(
        dependencies.context,
        claim_query or dependencies.context.question,
    )
    response = _resolve_precomputed_for_context(dependencies, context)
    if response is None or response.claim_channels is None:
        return GroundedToolAnswer(matched=False, reason="No claim-channel answer matched.")
    return dependencies.register(
        "claim_channels",
        with_demographics(response, context.insured),
        evidence=response_evidence(context, response),
    )


@function_tool
def retrieve_policy_terms(
    wrapper: RunContextWrapper[QaAgentDependencies],
    terms_query: str,
) -> GroundedToolAnswer:
    """Retrieve uploaded policy terms for payment conditions, exclusions, or waiting periods."""

    dependencies = wrapper.context
    context = context_with_question(
        dependencies.context,
        terms_query or dependencies.context.question,
    )
    response = _resolve_precomputed_for_context(dependencies, context)
    if response is None:
        return GroundedToolAnswer(matched=False, reason="No uploaded policy terms matched.")
    return dependencies.register(
        "policy_terms",
        with_demographics(response, context.insured),
        evidence=response_evidence(context, response),
    )


@function_tool
def answer_from_grounded_qa_tools(
    wrapper: RunContextWrapper[QaAgentDependencies],
) -> GroundedToolAnswer:
    """Return the existing deterministic, Official RAG, or Policy RAG answer when it matches."""

    dependencies = wrapper.context
    context = dependencies.context
    response = _resolve_grounded_answer(dependencies)
    if response is None:
        return GroundedToolAnswer(
            matched=False,
            reason="No deterministic or RAG answer matched.",
        )
    return dependencies.register(
        "grounded",
        with_demographics(response, context.insured),
        evidence=response_evidence(context, response),
    )


@function_tool
def answer_from_portfolio_consultation(
    wrapper: RunContextWrapper[QaAgentDependencies],
) -> GroundedToolAnswer:
    """Return the portfolio evidence from which the agent must write its answer."""

    dependencies = wrapper.context
    context = dependencies.context
    grounded_response = _resolve_grounded_answer(dependencies)
    if grounded_response is not None:
        return dependencies.register(
            "grounded",
            grounded_response,
            evidence=response_evidence(context, grounded_response),
        )

    evidence = consultation_evidence(context) or portfolio_snapshot_evidence(context)
    if not evidence:
        return GroundedToolAnswer(
            matched=False,
            reason="No uploaded-policy evidence is relevant to this question.",
        )
    response = PortfolioQuestionResponse(
        status="answered",
        answer="제공된 evidence 중 질문과 직접 관련된 항목만 골라 상담 답변을 작성하세요.",
        citations=[],
        limitations=standard_limitations(context.facts),
        suggestions=contextual_suggestions(context),
    )
    return dependencies.register(
        "consultation",
        with_demographics(response, context.insured),
        evidence=evidence,
    )


@function_tool
def search_official_web(
    wrapper: RunContextWrapper[QaAgentDependencies],
    purpose: SearchPurpose,
) -> GroundedToolAnswer:
    """Search only pre-approved official, association, or held-insurer domains."""

    context = wrapper.context.context
    allowed_domains = search_allowed_domains(context, purpose)
    result = wrapper.context.web_search(
        sanitize_search_query(context.question),
        purpose=purpose,
        allowed_domains=allowed_domains,
    )
    return wrapper.context.register(
        "web",
        web_search_response(result),
    )


def web_search_response(result: WebSearchResult) -> PortfolioQuestionResponse:
    if result.status != "searched" or not result.answer.strip() or not result.source_urls:
        limitation = result.limitation or "허용된 공식 웹사이트에서 근거를 확인하지 못했어요."
        return PortfolioQuestionResponse(
            status="no_data",
            answer=(
                "최신 공식 안내를 확인하지 못했어요. 허용된 공식 웹사이트에서 "
                "출처가 확인되는 결과를 찾지 못했습니다."
            ),
            citations=[],
            limitations=[limitation],
            suggestions=[],
        )

    citations = [
        AnswerCitation(
            policy_id=None,
            insurer=None,
            product_name=None,
            source_id=url,
            source_title=urlparse(url).hostname,
            source_category="official_web",
            source_url=url,
        )
        for url in result.source_urls
    ]
    return PortfolioQuestionResponse(
        status="answered",
        answer=f"최신 공식 안내를 찾아봤어요.\n\n{result.answer.strip()}",
        citations=citations,
        limitations=["공개된 공식 웹사이트에서 확인한 현재 안내예요."],
        suggestions=[],
        generation="llm",
    )


def _resolve_grounded_answer(
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse | None:
    if dependencies.grounded_checked:
        return dependencies.grounded_response

    context = dependencies.context
    response = _resolve_precomputed_for_context(dependencies, context)
    dependencies.grounded_checked = True
    dependencies.grounded_response = (
        with_demographics(response, context.insured) if response is not None else None
    )
    return dependencies.grounded_response


def _resolve_precomputed_for_context(
    dependencies: QaAgentDependencies,
    context: QaContext,
) -> PortfolioQuestionResponse | None:
    key = context.question
    if key in dependencies.precomputed_responses:
        return dependencies.precomputed_responses[key]

    response = resolve_precomputed_answer(
        context,
        try_official=True,
        official_answer=dependencies.official_answer,
        default_official_answer=answer_official_question,
        complete=dependencies.complete,
        pass_complete=True,
        retrieve_policy=retrieve_policy_context,
        generate_policy=generate_policy_answer,
    )
    dependencies.precomputed_responses[key] = response
    return response
