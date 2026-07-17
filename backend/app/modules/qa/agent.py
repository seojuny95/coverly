"""Agent SDK orchestration for grounded portfolio Q&A."""

import re
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

from agents import Agent, ModelSettings, RunConfig, RunContextWrapper, Runner, function_tool
from agents.models.openai_provider import OpenAIProvider
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.integrations.openai.client import JsonCompleter
from app.modules.coverage.matching import canonicalize_coverage_name, query_contains_canonical_name
from app.modules.coverage.taxonomy import CANCER, classify_coverage
from app.modules.evidence.catalog import (
    citation_from_evidence,
    is_safe_analysis_text,
    valid_evidence_ids,
)
from app.modules.policy.demographics import mask_demographic_identifiers
from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.context import QaContext, context_with_question
from app.modules.qa.contracts import ConsultationEvidence
from app.modules.qa.resolvers import (
    OfficialAnswerer,
    contextual_suggestions,
    resolve_precomputed_answer,
    standard_limitations,
    with_demographics,
)
from app.modules.qa.schemas import AnswerCitation, PortfolioQuestionResponse
from app.modules.qa.web_search import (
    OfficialWebSearcher,
    SearchPurpose,
    WebSearchResult,
    default_official_web_search,
    sanitize_search_query,
    search_allowed_domains,
)
from app.rag.official.answer import answer_official_question
from app.rag.policy import generate_policy_answer, retrieve_policy_context


class QaAgentUnavailable(RuntimeError):
    """Raised when the live Agent SDK path cannot be used."""


class QaAgentRunner(Protocol):
    def run(self, context: QaContext) -> PortfolioQuestionResponse: ...


@dataclass
class QaAgentDependencies:
    context: QaContext
    complete: JsonCompleter | None
    official_answer: OfficialAnswerer | None
    web_search: OfficialWebSearcher
    tool_results: dict[str, "RegisteredToolResult"] = field(default_factory=dict)
    grounded_checked: bool = False
    grounded_response: PortfolioQuestionResponse | None = None

    def register(
        self,
        kind: str,
        response: PortfolioQuestionResponse,
        *,
        evidence: tuple[ConsultationEvidence, ...] = (),
    ) -> "GroundedToolAnswer":
        result_id = f"{kind}:{len(self.tool_results) + 1}"
        self.tool_results[result_id] = RegisteredToolResult(
            kind=kind,
            response=response,
            evidence=evidence,
        )
        return GroundedToolAnswer(
            result_id=result_id,
            matched=True,
            response=response,
            evidence=list(evidence),
        )


@dataclass(frozen=True)
class RegisteredToolResult:
    kind: str
    response: PortfolioQuestionResponse
    evidence: tuple[ConsultationEvidence, ...] = ()


class GroundedToolAnswer(BaseModel):
    result_id: str | None = None
    matched: bool
    response: PortfolioQuestionResponse | None = None
    evidence: list[ConsultationEvidence] = Field(default_factory=list)
    reason: str | None = None


class AgentCounselorDraft(BaseModel):
    selected_result_id: str
    answer: str = Field(min_length=1, max_length=4_000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)


class PolicyFact(BaseModel):
    policy_id: str | None = None
    insurer: str | None = None
    product_name: str | None = None
    classification: str | None = None
    tags: list[str] = Field(default_factory=list)
    coverages: list[str] = Field(default_factory=list)


class AllPolicyFacts(BaseModel):
    policies: list[PolicyFact]
    evidence: list[ConsultationEvidence]


def build_qa_agent_runner(
    *,
    complete: JsonCompleter | None = None,
    official_answer: OfficialAnswerer | None = None,
    web_search: OfficialWebSearcher = default_official_web_search,
) -> QaAgentRunner:
    return OpenAiQaAgentRunner(
        complete=complete,
        official_answer=official_answer,
        web_search=web_search,
    )


class OpenAiQaAgentRunner:
    """Run a single OpenAI Agent that can call local QA tools."""

    def __init__(
        self,
        *,
        complete: JsonCompleter | None = None,
        official_answer: OfficialAnswerer | None = None,
        web_search: OfficialWebSearcher = default_official_web_search,
    ) -> None:
        self._complete = complete
        self._official_answer = official_answer
        self._web_search = web_search

    def run(self, context: QaContext) -> PortfolioQuestionResponse:
        settings = get_settings()
        if not settings.openai_api_key:
            raise QaAgentUnavailable("OPENAI_API_KEY is not configured")

        dependencies = QaAgentDependencies(
            context=context,
            complete=self._complete,
            official_answer=self._official_answer,
            web_search=self._web_search,
        )
        result = Runner.run_sync(
            _agent(
                settings.openai_model,
                required_first_tool=_required_first_tool(context),
            ),
            input=_agent_input(context),
            context=dependencies,
            max_turns=5,
            run_config=RunConfig(
                model_provider=OpenAIProvider(api_key=settings.openai_api_key),
                tracing_disabled=True,
                trace_include_sensitive_data=False,
                workflow_name="Coverly grounded QA",
            ),
        )
        draft = result.final_output_as(AgentCounselorDraft, raise_if_incorrect_type=True)
        return _validated_agent_response(context, draft, dependencies)


def _agent(
    model: str,
    *,
    required_first_tool: str | None = None,
) -> Agent[QaAgentDependencies]:
    return Agent[QaAgentDependencies](
        name="Coverly Q&A Agent",
        model=model,
        instructions=_agent_instructions(),
        tools=[
            list_policies,
            find_coverages,
            calculate_coverage_total,
            find_overlapping_coverages,
            get_claim_channels,
            retrieve_policy_terms,
            answer_from_grounded_qa_tools,
            answer_from_portfolio_consultation,
            search_official_web,
        ],
        output_type=AgentCounselorDraft,
        model_settings=ModelSettings(
            tool_choice=required_first_tool,
            parallel_tool_calls=False,
        ),
    )


def _agent_input(context: QaContext) -> str:
    history = "\n".join(
        f"{'사용자' if message.role == 'user' else '상담사'}: {message.content}"
        for message in context.history[-12:]
    )
    conversation = f"\n\n이전 대화:\n{history}" if history else ""
    prompt = (
        "사용자 질문에 답하세요.\n"
        f"지금 답할 질문: {context.question}{conversation}\n\n"
        "최신·현재 안내나 최근 변경을 묻는 질문이면 search_official_web을 먼저 호출하세요. "
        "법·제도 변경은 law_update, 보험사 안내는 insurer_guidance, 공개 약관은 "
        "public_policy_reference, 용어 설명은 insurance_term purpose를 사용하세요. "
        "사용자의 업로드 증권 질문은 아래 구조화 도구 중 필요한 것을 직접 고르세요: "
        "list_policies, find_coverages, calculate_coverage_total, find_overlapping_coverages, "
        "get_claim_channels, retrieve_policy_terms. "
        "어떤 구조화 도구도 맞지 않으면 answer_from_grounded_qa_tools를 호출하고, "
        "그래도 matched=false이면 사용자 증권의 비교·분석·상담은 "
        "answer_from_portfolio_consultation을 호출하세요. "
        "법, 제도, 보험 용어처럼 증권 밖의 사실을 묻는 질문은 search_official_web을 호출하세요. "
        "반드시 matched=true인 도구 결과 하나의 result_id를 선택해 최종 출력에 넣으세요."
    )
    return mask_demographic_identifiers(prompt)


def _agent_instructions() -> str:
    return """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 보험 상담사입니다.

원칙:
- 특정 상품 가입, 해지, 증액을 지시하지 않습니다.
- 보상 가능 여부, 면책, 지급액을 단정하지 않습니다.
- 도구가 제공한 근거 밖의 담보, 금액, 조건을 지어내지 않습니다.
- 모든 보험증권은 보험분류와 상관없이 확인 대상입니다.
- 공개/공식 자료는 일반 안내이고, 사용자가 업로드한 증권 근거보다 우선하지 않습니다.
- 웹검색은 허용 도메인 안에서만 보조 근거로 사용합니다.
- 웹검색 결과만으로 사용자의 실제 가입 약관 보장 여부를 확정하지 않습니다.
- 질문 의도 판단은 당신이 하고, 가입 목록·담보 검색·금액 합산·중복 확인·청구 채널·약관 조회는
  반드시 도구 결과로 확인합니다.

응답:
- AgentCounselorDraft JSON 스키마로만 답하세요.
- selected_result_id에는 실제로 호출해 받은 matched=true 결과의 result_id만 넣으세요.
- 도구 응답과 evidence를 재료로 사용해 최종 answer를 직접 작성하세요.
- 질문에 먼저 답하고, 필요한 설명만 이어가세요. 근거 목록을 그대로 복사하거나 전부 나열하지 마세요.
- 기본 답변은 짧은 문단 두세 개로 끝내고, 사용자가 묻지 않은 항목까지 완전 탐색해 나열하지 마세요.
- evidence_ids에는 실제 답변에 사용한 evidence의 id만 넣으세요.
- 웹검색처럼 evidence가 없는 도구는 빈 배열로 둡니다.
- 친근한 해요체를 쓰되 과장된 공감, 상투적인 인사, "안심하세요" 같은 단정은 피하세요.
- 이전 대화에서 이미 확인한 내용은 반복하지 말고 지금 질문에 필요한 맥락만 이어가세요.
- 사용자의 가족관계, 자녀, 학교, 소득처럼 evidence에 없는 개인 상황을 추측하지 마세요.
- 겹치는 보장은 같은 담보가 여러 증권에서 확인되는지와 실손형 중복 가능성을 구분해 설명하세요.
- 겹치는 보장 질문에는 실제로 겹치는 항목부터 답하고, 겹치지 않는 전체 담보를 다시 나열하지 마세요.
- 겹치는 보장 답변에는 확인된 중복이 정액형인지 실손형인지 반드시 구분해 말하세요.
- 가입금액 합계와 각 증권별 구성금액을 구분하세요. 합계를 각 증권이 각각 가진 금액처럼 쓰지 마세요.
- 정액형 담보가 겹치면 보험사·상품별 구성금액을 말하세요.
- 정액형 중복을 불필요하다고 단정하지 말고 약관별 지급 조건 확인 필요를 짧게 설명하세요.
- 서로 다른 질병 담보라는 이유만으로 "겹침이 없다"고 결론내리지 마세요.
- 법·제도·용어 질문에는 사용자 증권 담보를 억지로 연결하지 마세요.
- 강점은 실제 담보명과 가입금액 근거로 설명하고, 위험 분산·완벽한 대비·어떤 상황에서도
  대응 가능하다는 일반적인 칭찬을 만들지 마세요.
- 강점 질문은 근거가 분명한 핵심 두세 개만 말하고, 사용자가 묻지 않은 공백이나 추가 가입
  제안을 덧붙이지 마세요. 가입금액은 지급 확정액이 아니므로 "지급됩니다", "보장받을 수
  있어요", "안심하세요"라고 표현하지 마세요.
- 사용자가 질병 진단이나 사고를 말하면 관련해 확인된 보유 담보와 가입금액부터 구체적으로 말하세요.
- 가입 사실·가입금액은 확정해서 말하고, 실제 지급 여부만 약관·진단서 확인이 필요하다고 구분하세요.
- 직전 대화의 진단에 이어 "내 보험으로 받을 수 있어?"라고 물으면 그 진단 맥락을 유지하세요.
"""


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
        evidence=_response_evidence(context, response),
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
            evidence=_response_evidence(context, response),
        )

    context = context_with_question(dependencies.context, query or dependencies.context.question)
    evidence = _consultation_evidence(context)
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
        evidence=_response_evidence(context, response),
    )


@function_tool
def find_overlapping_coverages(
    wrapper: RunContextWrapper[QaAgentDependencies],
) -> GroundedToolAnswer:
    """Find duplicate fixed-benefit coverages or repeated actual-loss coverages."""

    dependencies = wrapper.context
    context = context_with_question(dependencies.context, "겹치는 보장이 있는지 확인해줘")
    evidence = _consultation_evidence(context)
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
        evidence=_response_evidence(context, response),
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
        evidence=_response_evidence(context, response),
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
        evidence=_response_evidence(context, response),
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
            evidence=_response_evidence(context, grounded_response),
        )

    evidence = _consultation_evidence(context)
    if not evidence:
        return GroundedToolAnswer(
            matched=False,
            reason="No uploaded-policy evidence is relevant to this question.",
        )
    response = PortfolioQuestionResponse(
        status="answered",
        answer="질문과 직접 관련된 evidence만 골라 상담 답변을 작성하세요.",
        citations=[],
        limitations=standard_limitations(context.facts),
        suggestions=contextual_suggestions(context),
    )
    return dependencies.register(
        "consultation",
        with_demographics(response, context.insured),
        evidence=evidence,
    )


_OVERLAP_QUESTION_TERMS = ("겹치", "중복")
_OVERLAP_EVIDENCE_TERMS = (
    "같은 담보명",
    "여러 계약에서 같은 실손형",
)
_BROAD_PORTFOLIO_TERMS = (
    "강점",
    "약점",
    "부족",
    "비어",
    "전체",
    "정리",
    "분석",
    "어떻게 봐",
    "보험료",
    "유지",
    "해지",
)
_SECONDARY_CANCER_COVERAGE_TERMS = ("유사암", "재진단", "전이암", "소액암")


def _consultation_evidence(context: QaContext) -> tuple[ConsultationEvidence, ...]:
    question = context.question
    if any(term in question for term in _OVERLAP_QUESTION_TERMS):
        return tuple(
            item
            for item in context.catalog.items
            if item.id == "portfolio:no-overlap"
            or any(term in item.fact for term in _OVERLAP_EVIDENCE_TERMS)
        )
    if any(term in question for term in _BROAD_PORTFOLIO_TERMS):
        return context.catalog.items

    evidence_ids: list[str] = []
    category = classify_coverage(question)
    if category is None and "암" in "".join(question.split()):
        category = CANCER
    if category is not None:
        evidence_ids.extend(context.catalog.coverage_ids_by_category.get(category, ()))

    for item in context.catalog.items:
        coverage_key = (
            canonicalize_coverage_name(item.coverage_name).normalized_key
            if item.coverage_name
            else None
        )
        if (
            (coverage_key and query_contains_canonical_name(question, coverage_key))
            or (item.insurer and item.insurer in question)
            or (item.product_name and item.product_name in question)
        ):
            evidence_ids.append(item.id)

    evidence = tuple(
        context.catalog.by_id[evidence_id]
        for evidence_id in dict.fromkeys(evidence_ids)
        if evidence_id in context.catalog.by_id
    )
    if category == CANCER and "유사암" not in question:
        primary = tuple(
            item
            for item in evidence
            if item.coverage_name is None
            or not any(
                term in item.coverage_name.split("(")[0].strip()
                for term in _SECONDARY_CANCER_COVERAGE_TERMS
            )
        )
        return primary or evidence
    return evidence


def _resolve_grounded_answer(
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse | None:
    if dependencies.grounded_checked:
        return dependencies.grounded_response

    context = dependencies.context
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
    dependencies.grounded_checked = True
    dependencies.grounded_response = (
        with_demographics(response, context.insured) if response is not None else None
    )
    return dependencies.grounded_response


def _resolve_precomputed_for_context(
    dependencies: QaAgentDependencies,
    context: QaContext,
) -> PortfolioQuestionResponse | None:
    return resolve_precomputed_answer(
        context,
        try_official=True,
        official_answer=dependencies.official_answer,
        default_official_answer=answer_official_question,
        complete=dependencies.complete,
        pass_complete=True,
        retrieve_policy=retrieve_policy_context,
        generate_policy=generate_policy_answer,
    )


@function_tool
def list_all_policy_facts(wrapper: RunContextWrapper[QaAgentDependencies]) -> AllPolicyFacts:
    """List every uploaded policy regardless of insurance classification."""

    context = wrapper.context.context
    return AllPolicyFacts(
        policies=[_policy_fact(policy) for policy in context.policies],
        evidence=list(context.catalog.items),
    )


@function_tool
def search_official_web(
    wrapper: RunContextWrapper[QaAgentDependencies],
    query: str,
    purpose: SearchPurpose,
) -> GroundedToolAnswer:
    """Search only pre-approved official, association, or held-insurer domains."""

    del query
    context = wrapper.context.context
    allowed_domains = search_allowed_domains(context, purpose)
    result = wrapper.context.web_search(
        sanitize_search_query(context.question),
        purpose=purpose,
        allowed_domains=allowed_domains,
    )
    return wrapper.context.register(
        "web",
        _web_search_response(context, result),
    )


def _policy_fact(policy: PolicyInput) -> PolicyFact:
    return PolicyFact(
        policy_id=policy.id,
        insurer=policy.기본정보.보험사,
        product_name=policy.기본정보.상품명,
        classification=policy.기본정보.보험분류,
        tags=list(policy.기본정보.상품태그),
        coverages=[coverage.담보명 for coverage in policy.보장목록],
    )


def _web_search_response(
    context: QaContext,
    result: WebSearchResult,
) -> PortfolioQuestionResponse:
    del context
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


def _validated_agent_response(
    context: QaContext,
    draft: AgentCounselorDraft,
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse:
    selected = _select_tool_result(context, draft, dependencies)
    if selected is None and _requires_official_web(context.question):
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


def _response_evidence(
    context: QaContext,
    response: PortfolioQuestionResponse,
) -> tuple[ConsultationEvidence, ...]:
    evidence: list[ConsultationEvidence] = []
    for citation in response.citations:
        if citation.evidence_id is None:
            continue
        item = context.catalog.by_id.get(citation.evidence_id)
        if item is not None:
            evidence.append(item)
    return tuple(evidence)


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
    selected = dependencies.tool_results.get(draft.selected_result_id)
    if _requires_official_web(context.question):
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


def _requires_official_web(question: str) -> bool:
    return any(term in question for term in _LATEST_INFORMATION_TERMS) and any(
        term in question for term in _OFFICIAL_WEB_TOPIC_TERMS
    )


def requires_official_web(question: str) -> bool:
    """Return whether this turn must be grounded in a fresh official web search."""

    return _requires_official_web(question)


def _required_first_tool(context: QaContext) -> str | None:
    if _requires_official_web(context.question):
        return "search_official_web"
    return None


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
