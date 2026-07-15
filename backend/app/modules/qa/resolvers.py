"""Resolve QA questions with deterministic, policy, and official-source strategies."""

from collections.abc import Callable
from typing import Protocol

from app.integrations.openai.client import JsonCompleter
from app.modules.coverage.matching import (
    canonicalize_coverage_name,
    query_contains_canonical_name,
)
from app.modules.coverage.taxonomy import LifeStageCheck
from app.modules.evidence.catalog import (
    EvidenceCatalog,
    citation_from_evidence,
    with_session_evidence,
)
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.summary import PortfolioFacts, is_auto_policy
from app.modules.qa.claim_channels import claim_channel_block
from app.modules.qa.context import QaContext
from app.modules.qa.contracts import AnswerSection, ConsultationEvidence, InsuredDemographics
from app.modules.qa.schemas import AnswerCitation, PortfolioQuestionResponse
from app.rag.official.answer import RagAnswer, RagCitation
from app.rag.policy import PolicyGenerationResult, PolicyRetrievalHit

_CLAIM_HOWTO_TERMS = ("청구", "신청", "접수", "서류")
_AUTO_CLAIM_TERMS = ("자동차", "사고", "대물", "대인", "접촉", "추돌", "차량", "주차")
_AMOUNT_TERMS = ("합계", "총액", "얼마", "가입금액")
_STATUS_TERMS = ("추출 상태", "분석 상태", "제외된", "확인 못한")
_HOLDING_TERMS = ("몇 개", "몇개", "몇 건", "몇건", "보유 중", "목록", "가입한 보험")
_OFFICIAL_RAG_TERMS = (
    "계약 전 알릴 의무",
    "고지의무",
    "알릴 의무",
    "면책",
    "지급사유",
    "보상하지 않는",
    "지급하지 않는",
    "감액",
    "대기기간",
    "표준약관",
    "보험약관",
    "용어",
)
_OFFICIAL_CLAIM_CHECK_TERMS = (
    "보상",
    "보험금",
    "지급",
    "받을 수",
    "받을수",
    "면책",
)
_MAX_SUGGESTIONS = 3

OfficialAnswerer = Callable[[str], RagAnswer]
PolicyContextRetriever = Callable[[list[str], str], list[PolicyRetrievalHit]]


class PolicyAnswerGenerator(Protocol):
    def __call__(
        self,
        question: str,
        evidence: tuple[ConsultationEvidence, ...],
        *,
        complete: JsonCompleter | None = None,
    ) -> PolicyGenerationResult: ...


def resolve_precomputed_answer(
    context: QaContext,
    *,
    try_official: bool,
    official_answer: OfficialAnswerer | None,
    default_official_answer: OfficialAnswerer,
    complete: JsonCompleter | None,
    pass_complete: bool,
    retrieve_policy: PolicyContextRetriever,
    generate_policy: PolicyAnswerGenerator,
) -> PortfolioQuestionResponse | None:
    if try_official:
        response = _answer_with_official_rag(
            context.question,
            official_answer or default_official_answer,
        )
        if response is not None:
            return with_demographics(response, context.insured)

    if not context.facts.policies and not context.auto_policies:
        return with_demographics(_no_uploaded_policies_response(), context.insured)
    if any(term in context.question for term in _AMOUNT_TERMS):
        response = _answer_amount(context.question, context.facts, context.catalog)
        return with_demographics(response, context.insured)
    if any(term in context.question for term in _STATUS_TERMS):
        response = _answer_status(context.facts, context.catalog, context.auto_policies)
        return with_demographics(response, context.insured)
    if any(term in context.question for term in _HOLDING_TERMS):
        response = _answer_holdings(context.facts, context.catalog, context.auto_policies)
        return with_demographics(response, context.insured)
    if any(term in context.question for term in _CLAIM_HOWTO_TERMS):
        response = _answer_claim_channels(context.policies, context.facts, context.question)
        return with_demographics(response, context.insured)

    policy_catalog = _policy_session_catalog(
        context.catalog,
        context.policies,
        context.question,
        retrieve_policy,
    )
    if policy_catalog is None:
        return None

    if pass_complete:
        result = generate_policy(
            context.question,
            policy_catalog.items,
            complete=complete,
        )
    else:
        result = generate_policy(context.question, policy_catalog.items)
    response = _policy_generation_response(result, policy_catalog, context_fallback(context))
    return with_demographics(response, context.insured)


def context_fallback(context: QaContext) -> PortfolioQuestionResponse:
    return _consultation_fallback(
        context.facts,
        context.insured,
        context.life_stage_check,
        context.catalog,
    )


def contextual_suggestions(context: QaContext) -> list[str]:
    totals = context.facts.coverage_summary.totals
    if totals:
        coverage_name = totals[0].display_name
        candidates = [
            f"{coverage_name} 가입금액은 얼마야?",
            f"{coverage_name} 지급 조건은 뭐야?",
            "가입한 보험은 몇 개야?",
        ]
    else:
        candidates = [
            "가입한 보험은 몇 개야?",
            "분석 상태는 어때?",
            "실손 청구는 어디서 해?",
        ]
    if context.facts.coverage_summary.indemnity_coverages:
        candidates.append("실손 청구는 어디서 해?")
    return question_suggestions(*candidates)


def question_suggestions(*candidates: str) -> list[str]:
    suggestions: list[str] = []
    for candidate in candidates:
        cleaned = " ".join(candidate.split())
        if not cleaned or cleaned in suggestions or not cleaned.endswith("?"):
            continue
        suggestions.append(cleaned)
        if len(suggestions) == _MAX_SUGGESTIONS:
            break
    return suggestions


def standard_limitations(facts: PortfolioFacts) -> list[str]:
    summary = facts.coverage_summary
    limitations = ["보상 조건·면책·지급 가능성은 약관 근거 없이 판단하지 않습니다."]
    if summary.indemnity_coverages:
        limitations.append("실손형 담보는 가입금액 합계에 포함하지 않았습니다.")
    if summary.excluded_coverages:
        limitations.append("지급유형 또는 금액이 확인되지 않은 담보는 합계에 포함하지 않았습니다.")
    if summary.damage_coverages:
        limitations.append(
            "손해보험은 종류별 보장금으로 따로 표시하고 가입금액 합계에는 포함하지 않았어요."
        )
    return limitations


def demographic_notice(demographics: InsuredDemographics) -> str | None:
    return {
        "conflict": "증권별 피보험자 정보가 서로 달라 나이·성별 개인화를 적용하지 않았습니다.",
        "conflict_user_override": (
            "증권별 피보험자 정보가 서로 달라 사용자가 확인한 정보로 개인화했습니다."
        ),
        "missing": "증권에서 피보험자 나이·성별을 확인하지 못해 개인화를 적용하지 않았습니다.",
    }.get(demographics.status)


def with_demographics(
    response: PortfolioQuestionResponse,
    demographics: InsuredDemographics,
) -> PortfolioQuestionResponse:
    limitations = list(response.limitations)
    notice = demographic_notice(demographics)
    if notice and notice not in limitations:
        limitations.append(notice)
    return response.model_copy(update={"demographics": demographics, "limitations": limitations})


def _no_uploaded_policies_response() -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="no_data",
        answer="**살펴볼 보험 정보가 아직 없어요.**\n\n- 보험증권을 먼저 업로드해 주세요.",
        citations=[],
        limitations=["보험증권을 먼저 업로드해 주세요."],
        suggestions=["업로드한 증권에서 어떤 보장을 확인할 수 있어?"],
    )


def _policy_session_catalog(
    catalog: EvidenceCatalog,
    policies: list[PolicyInput],
    question: str,
    retrieve_policy: PolicyContextRetriever,
) -> EvidenceCatalog | None:
    session_ids = [policy.문서세션ID for policy in policies if policy.문서세션ID is not None]
    if not session_ids:
        return None
    try:
        hits = retrieve_policy(session_ids, question)
    except Exception:
        # Session RAG is optional. Retrieval outages must fall through to the
        # portfolio-fact or consultation path instead of failing the whole answer.
        return None
    if not hits:
        return None
    return with_session_evidence(catalog, hits)


def _policy_generation_response(
    result: PolicyGenerationResult,
    catalog: EvidenceCatalog,
    fallback: PortfolioQuestionResponse,
) -> PortfolioQuestionResponse:
    if result.generation == "fallback":
        return fallback

    section = AnswerSection(
        title="업로드 증권 근거",
        content=result.answer,
        basis="confirmed_fact",
    )
    return PortfolioQuestionResponse(
        status="answered",
        answer=_markdown_section("업로드 증권 근거", result.answer),
        sections=[section],
        citations=[
            citation_from_evidence(catalog.by_id[item_id]) for item_id in result.evidence_ids
        ],
        limitations=list(result.limitations),
        suggestions=list(result.suggestions),
        generation="llm",
    )


def _answer_with_official_rag(
    question: str,
    answerer: OfficialAnswerer,
) -> PortfolioQuestionResponse | None:
    if not _should_try_official_rag(question):
        return None
    try:
        result = answerer(question)
    except Exception:
        # Official RAG is a shortcut, not a requirement. A pgvector or OpenAI
        # outage falls through to the remaining grounded answer strategies.
        return None
    if result.status != "answered":
        return None

    section = AnswerSection(
        title="공식자료 기준 일반 안내",
        content=result.answer,
        basis="general_guidance",
    )
    return PortfolioQuestionResponse(
        status="answered",
        answer=_markdown_section("공식자료 기준 일반 안내", result.answer),
        sections=[section],
        citations=[_official_citation(citation) for citation in result.citations],
        limitations=list(result.limitations),
        suggestions=_official_suggestions(result),
        generation="llm",
    )


def _should_try_official_rag(question: str) -> bool:
    if any(term in question for term in _AMOUNT_TERMS):
        return False
    if any(term in question for term in _CLAIM_HOWTO_TERMS):
        return False
    if any(term in question for term in _OFFICIAL_RAG_TERMS):
        return True
    claimish = any(term in question for term in _OFFICIAL_CLAIM_CHECK_TERMS)
    check_intent = any(
        term in question
        for term in ("기준", "확인", "가능", "보상돼", "보상되", "받을 수", "받을수", "나와")
    )
    return claimish and check_intent


def _official_citation(citation: RagCitation) -> AnswerCitation:
    return AnswerCitation(
        evidence_id=citation.chunk_id,
        policy_id=None,
        insurer=None,
        product_name=None,
        coverage_name=None,
        source_id=citation.source_id,
        source_title=citation.source_title,
        source_category=citation.source_category,
        source_url=citation.source_url,
        source_page=citation.page_start,
        source_version=citation.version_label,
    )


def _official_suggestions(result: RagAnswer) -> list[str]:
    if result.mode == "claim_check":
        return question_suggestions("내 증권 기준으로도 보상 조건을 확인할 수 있어?")
    return question_suggestions(
        "이 약관 내용이 내 증권에도 들어 있어?",
        "내 담보의 지급 조건은 뭐야?",
    )


def _answer_holdings(
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
    auto_policies: tuple[PolicyInput, ...] = (),
) -> PortfolioQuestionResponse:
    labels: list[str] = []
    evidence_ids: list[str] = []
    policy_evidence = [item for item in catalog.items if item.id.startswith("policy:")]
    for policy, evidence in zip(facts.policies, policy_evidence, strict=True):
        insurer = policy.기본정보.보험사 or "보험사 미확인"
        product = policy.기본정보.상품명 or "상품명 미확인"
        classification = policy.기본정보.보험분류 or "미분류"
        labels.append(f"{insurer} {product}({classification})")
        evidence_ids.append(evidence.id)

    auto_evidence = [item for item in catalog.items if item.id.startswith("auto:")]
    for policy, evidence in zip(auto_policies, auto_evidence, strict=True):
        insurer = policy.기본정보.보험사 or "보험사 미확인"
        product = policy.기본정보.상품명 or "상품명 미확인"
        labels.append(f"{insurer} {product}(자동차)")
        evidence_ids.append(evidence.id)

    items = "\n".join(f"- {label}" for label in labels)
    content = f"업로드된 보험은 **{len(labels)}건**이에요.\n\n{items}"
    return _fact_response(content, evidence_ids, catalog, facts)


def _answer_amount(
    question: str,
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
) -> PortfolioQuestionResponse:
    selected_totals = facts.coverage_summary.totals
    if not _is_overall_amount_question(question):
        matches = [
            total
            for total in facts.coverage_summary.totals
            if query_contains_canonical_name(question, total.normalized_name)
        ]
        matches.sort(key=lambda total: len(total.normalized_name), reverse=True)
        if len(matches) > 1:
            return PortfolioQuestionResponse(
                status="no_data",
                answer=(
                    "**질문과 일치하는 담보가 여러 개**라 하나의 가입금액으로 답하기 어려워요.\n\n"
                    "- 증권에 적힌 담보명 하나를 지정해 주세요."
                ),
                citations=[],
                limitations=standard_limitations(facts),
                suggestions=question_suggestions("담보별 가입금액은 얼마야?"),
            )
        selected_totals = matches

    if not selected_totals:
        return PortfolioQuestionResponse(
            status="no_data",
            answer=(
                "**확인 가능한 가입금액을 찾지 못했어요.**\n\n"
                "- 올린 증권에서 질문한 담보명과 일치하는 항목을 찾지 못했습니다."
            ),
            citations=[],
            limitations=standard_limitations(facts),
            suggestions=_fact_suggestions(facts),
        )

    total_amount = sum(item.total_amount for item in selected_totals)
    selected_names = {item.normalized_name for item in selected_totals}
    evidence_ids = [
        evidence.id
        for evidence in catalog.items
        if evidence.amount is not None
        and evidence.coverage_name is not None
        and canonicalize_coverage_name(evidence.coverage_name).normalized_key in selected_names
    ]
    if len(selected_totals) == 1:
        content = (
            f"**{selected_totals[0].display_name}**의 확인 가능한 가입금액 합계는 "
            f"**{total_amount:,}원**이에요."
        )
    else:
        items = "\n".join(f"- {total.display_name}" for total in selected_totals)
        content = (
            f"확인 가능한 정액형 담보 **{len(selected_totals)}종**의 가입금액 합계는 "
            f"**{total_amount:,}원**이에요.\n\n{items}"
        )
    return _fact_response(content, evidence_ids, catalog, facts)


def _answer_status(
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
    auto_policies: tuple[PolicyInput, ...] = (),
) -> PortfolioQuestionResponse:
    summary = facts.coverage_summary
    auto_note = f", 자동차보험 {len(auto_policies)}건" if auto_policies else ""
    content = "\n".join(
        [
            f"- 비자동차 보험: **{len(facts.policies)}건**{auto_note}",
            f"- 정액형 합계: **{len(summary.totals)}종**",
            f"- 실손형: **{len(summary.indemnity_coverages)}건**",
            f"- 합계 제외: **{len(summary.excluded_coverages)}건**",
        ]
    )
    evidence_ids = [item.id for item in catalog.items]
    return _fact_response(content, evidence_ids, catalog, facts)


def _fact_response(
    content: str,
    evidence_ids: list[str],
    catalog: EvidenceCatalog,
    facts: PortfolioFacts,
) -> PortfolioQuestionResponse:
    section = AnswerSection(
        title="증권에서 확인된 사실",
        content=content,
        basis="confirmed_fact",
    )
    return PortfolioQuestionResponse(
        status="answered",
        answer=_markdown_section("증권에서 확인된 사실", content),
        sections=[section],
        citations=[
            citation_from_evidence(catalog.by_id[evidence_id])
            for evidence_id in dict.fromkeys(evidence_ids)
            if evidence_id in catalog.by_id
        ],
        limitations=standard_limitations(facts),
        suggestions=_fact_suggestions(facts),
    )


def _consultation_fallback(
    facts: PortfolioFacts,
    demographics: InsuredDemographics,
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
) -> PortfolioQuestionResponse:
    held = list(life_stage_check.held)
    missing = list(life_stage_check.missing)
    if held:
        confirmed = f"현재 증권에서 {', '.join(held)} 관련 담보를 확인했어요."
        evidence_ids = [
            evidence_id
            for category in held
            for evidence_id in catalog.coverage_ids_by_category.get(category, ())
        ]
    else:
        confirmed = "현재 업로드된 증권의 가입 사실과 담보 목록을 확인했어요."
        evidence_ids = ["portfolio:summary"]

    if missing:
        guidance = (
            f"{', '.join(missing)} 항목은 현재 증권에서 확인되지 않았어요. "
            "곧바로 부족하다고 단정하기보다 필요 여부와 유지 가능한 예산을 "
            "함께 점검해 보세요."
        )
    elif demographics.age is None:
        guidance = (
            "증권에서 피보험자 나이를 확인하면 생애단계에 맞춘 검토 항목을 "
            "더 구체적으로 안내할 수 있어요."
        )
    else:
        guidance = (
            "확인된 가입금액을 소득, 치료 중 생활비, 부양 책임과 비교하면 "
            "개인 기준의 검토 우선순위를 정할 수 있어요."
        )

    sections = [
        AnswerSection(title="증권에서 확인된 사실", content=confirmed, basis="confirmed_fact"),
        AnswerSection(title="함께 살펴볼 제안", content=guidance, basis="general_guidance"),
    ]
    return PortfolioQuestionResponse(
        status="answered",
        answer="\n\n".join(
            _markdown_section(section.title, section.content) for section in sections
        ),
        sections=sections,
        citations=[
            citation_from_evidence(catalog.by_id[evidence_id])
            for evidence_id in dict.fromkeys(evidence_ids)
            if evidence_id in catalog.by_id
        ],
        limitations=standard_limitations(facts)
        + ["AI 상담 답변을 사용할 수 없어 확인된 사실 기반 안내를 표시합니다."],
        suggestions=[
            "현재 보장에서 먼저 확인할 항목은 무엇인가요?",
            "다음으로 확인하면 좋은 정보는 무엇인가요?",
        ],
    )


def _answer_claim_channels(
    policies: list[PolicyInput],
    facts: PortfolioFacts,
    question: str,
) -> PortfolioQuestionResponse:
    auto_related = any(term in question for term in _AUTO_CLAIM_TERMS)
    relevant = policies if auto_related else [p for p in policies if not is_auto_policy(p)]
    insurers = [policy.기본정보.보험사 for policy in relevant if policy.기본정보.보험사]
    block = claim_channel_block(
        insurers,
        has_indemnity=bool(facts.coverage_summary.indemnity_coverages),
    )
    lead_in = (
        "**청구는 아래 채널에서 확인하실 수 있어요.**\n\n"
        "1. 보험사 앱이나 홈페이지에서 청구 메뉴를 확인하세요.\n"
        "2. 진료비 영수증, 진단서 등 필요한 서류를 준비하세요.\n"
        "3. 실제 보상 가능 여부와 지급액은 보험사 심사로 확정돼요."
    )
    return PortfolioQuestionResponse(
        status="answered",
        answer=lead_in,
        sections=[AnswerSection(title="청구 방법 안내", content=lead_in, basis="general_guidance")],
        citations=[],
        limitations=[
            "청구 방법만 안내했어요. "
            "보상 가능 여부와 지급액은 약관·보험사 안내를 확인해야 정확합니다."
        ],
        suggestions=_fact_suggestions(facts),
        claim_channels=block,
    )


def _fact_suggestions(facts: PortfolioFacts) -> list[str]:
    totals = facts.coverage_summary.totals
    if not totals:
        return question_suggestions("가입한 보험은 몇 개야?", "분석 상태는 어때?")
    coverage_name = totals[0].display_name
    return question_suggestions(
        f"{coverage_name} 가입금액은 얼마야?",
        f"{coverage_name} 지급 조건은 뭐야?",
        "가입한 보험은 몇 개야?",
    )


def _is_overall_amount_question(question: str) -> bool:
    return any(term in question for term in ("전체", "총합", "모든", "총액"))


def _markdown_section(title: str, content: str) -> str:
    return f"**{title}**\n\n{content.strip()}"
