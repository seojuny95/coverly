"""Resolve QA questions with deterministic, policy, and official-source strategies."""

from collections.abc import Callable
from typing import Protocol

from app.integrations.openai.client import JsonCompleter
from app.modules.coverage.matching import (
    canonicalize_coverage_name,
    query_contains_canonical_name,
)
from app.modules.coverage.taxonomy import CANCER, CEREBRO, HEART, LifeStageCheck, classify_coverage
from app.modules.evidence.catalog import (
    EvidenceCatalog,
    citation_from_evidence,
    with_session_evidence,
)
from app.modules.portfolio.schemas import ActualLossCoverageItem, PolicyInput
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
_ADEQUACY_TERMS = ("적당", "적정", "충분", "권장", "추천", "얼마정도", "어느 정도")
_STATUS_TERMS = ("추출 상태", "분석 상태", "제외된", "확인 못한")
_HOLDING_TERMS = ("몇 개", "몇개", "몇 건", "몇건", "보유 중", "목록", "가입한 보험")
_MEDICAL_INDEMNITY_LOOKUP_TERMS = (
    "실비",
    "실손의료",
    "실손의료보험",
    "실손의료비",
    "실손보험",
)
_ACTUAL_LOSS_LOOKUP_TERMS = ("실손", "실손형", "비례보상")
_EXPLICIT_ACTUAL_LOSS_LOOKUP_TERMS = ("실손형", "실비형", "비례보상")
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
_POLICY_TERMS_QUESTION_TERMS = (
    "지급 조건",
    "지급조건",
    "지급사유",
    "면책",
    "보상하지 않는",
    "지급하지 않는",
    "감액",
    "대기기간",
)
_DIAGNOSIS_CATEGORIES = (CANCER, CEREBRO, HEART)
_DIAGNOSIS_EVENT_TERMS = (
    "진단받",
    "진단 받",
    "진단을 받",
    "확진",
    "판정받",
    "판정 받",
    "걸렸",
    "걸린",
    "발병",
)
_CLAIM_RELEVANCE_TERMS = (
    "보장",
    "보험금",
    "받을 수",
    "받을수",
    "나와",
    "청구",
    "어떻게",
    "뭘 해야",
)
_SECONDARY_CANCER_COVERAGE_TERMS = ("유사암", "재진단", "전이암", "소액암")
_EXPLICIT_COVERAGE_QUESTION_TERMS = (
    "진단비",
    "수술비",
    "입원비",
    "담보",
    "가입금액",
    "약관",
    "원문",
    "지급조건",
    "지급 조건",
    "확인기준",
    "확인 기준",
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
    if (
        _requires_policy_terms(context.question)
        and not any(term in context.question for term in _AMOUNT_TERMS)
        and _question_targets_held_coverage(context)
    ):
        policy_terms_response = _answer_policy_terms_question(
            context,
            complete=complete,
            pass_complete=pass_complete,
            retrieve_policy=retrieve_policy,
            generate_policy=generate_policy,
        )
        return with_demographics(policy_terms_response, context.insured)

    diagnosis_response = _answer_diagnosis_scenario(context)
    if diagnosis_response is not None:
        return with_demographics(diagnosis_response, context.insured)

    if try_official:
        response = _answer_with_official_rag(
            context.question,
            official_answer or default_official_answer,
        )
        if response is not None:
            return with_demographics(response, context.insured)

    if not _has_any_uploaded_policy_data(context):
        return with_demographics(_no_uploaded_policies_response(), context.insured)
    if _is_adequacy_question(context.question):
        response = _answer_adequacy_lookup(context.question, context.facts, context.catalog)
        if response is not None:
            return with_demographics(response, context.insured)
    if any(term in context.question for term in _AMOUNT_TERMS) and not _is_adequacy_question(
        context.question
    ):
        response = _answer_amount(context.question, context.facts, context.catalog)
        return with_demographics(response, context.insured)
    if _requires_policy_terms(context.question):
        response = _answer_policy_terms_question(
            context,
            complete=complete,
            pass_complete=pass_complete,
            retrieve_policy=retrieve_policy,
            generate_policy=generate_policy,
        )
        return with_demographics(response, context.insured)
    if any(term in context.question for term in _STATUS_TERMS):
        response = _answer_status(context.facts, context.catalog, context.auto_policies)
        return with_demographics(response, context.insured)
    if any(term in context.question for term in _HOLDING_TERMS):
        response = _answer_holdings(context.policies, context.facts, context.catalog)
        return with_demographics(response, context.insured)
    if any(term in context.question for term in _CLAIM_HOWTO_TERMS):
        response = _answer_claim_channels(context.policies, context.facts, context.question)
        return with_demographics(response, context.insured)
    response = _answer_coverage_lookup(context.question, context.facts, context.catalog)
    if response is not None:
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


def resolve_fast_answer(context: QaContext) -> PortfolioQuestionResponse | None:
    """Resolve portfolio facts without retrieval or model calls."""

    diagnosis_response = _answer_diagnosis_scenario(context)
    if diagnosis_response is not None:
        return with_demographics(diagnosis_response, context.insured)

    question = context.question
    is_adequacy = _is_adequacy_question(question)
    is_amount = (
        any(term in question for term in _AMOUNT_TERMS)
        and not is_adequacy
        and not _is_generic_amount_definition(context)
    )
    is_status = any(term in question for term in _STATUS_TERMS)
    is_holdings = any(term in question for term in _HOLDING_TERMS)
    is_claim_howto = any(term in question for term in _CLAIM_HOWTO_TERMS)

    if not _has_any_uploaded_policy_data(context):
        if any((is_adequacy, is_amount, is_status, is_holdings, is_claim_howto)):
            return with_demographics(_no_uploaded_policies_response(), context.insured)
        return None

    if is_adequacy:
        response = _answer_adequacy_lookup(question, context.facts, context.catalog)
        if response is not None:
            return with_demographics(response, context.insured)
    if is_amount:
        response = _answer_amount(question, context.facts, context.catalog)
        return with_demographics(response, context.insured)
    if is_status:
        response = _answer_status(context.facts, context.catalog, context.auto_policies)
        return with_demographics(response, context.insured)
    if is_holdings:
        response = _answer_holdings(context.policies, context.facts, context.catalog)
        return with_demographics(response, context.insured)
    if is_claim_howto:
        response = _answer_claim_channels(context.policies, context.facts, question)
        return with_demographics(response, context.insured)

    if _is_actual_loss_rule_question(question):
        return None
    response = _answer_coverage_lookup(question, context.facts, context.catalog)
    if response is not None:
        return with_demographics(response, context.insured)
    return None


def _answer_diagnosis_scenario(context: QaContext) -> PortfolioQuestionResponse | None:
    scenario = _diagnosis_scenario(context)
    if scenario is None:
        return None

    scenario_text, category = scenario
    evidence = _diagnosis_evidence(context.catalog, scenario_text, category)
    if not evidence:
        return None

    facts = "\n".join(f"- {item.fact}" for item in evidence)
    content = (
        "올려주신 증권을 기준으로, 말씀하신 진단과 관련해 먼저 확인할 보장이 있어요.\n\n"
        f"{facts}\n\n"
        "여기까지는 증권에서 확인된 가입 사실과 가입금액이에요. 실제 지급 여부는 "
        "진단서의 진단명·질병코드와 각 담보 약관의 지급사유를 대조해야 확정할 수 있어요. "
        "수술이나 항암치료를 받게 되면 관련 수술비·치료비 담보는 별도로 확인할 수 있어요."
    )
    insurers = _diagnosis_evidence_insurers(context, evidence)
    return PortfolioQuestionResponse(
        status="answered",
        answer=content,
        sections=[
            AnswerSection(
                title="증권에서 확인된 관련 보장",
                content=content,
                basis="confirmed_fact",
            )
        ],
        citations=[citation_from_evidence(item) for item in evidence],
        limitations=standard_limitations(context.facts),
        suggestions=question_suggestions(
            "암진단비 지급 조건은 뭐야?" if category == CANCER else "진단비 지급 조건은 뭐야?",
            "보험금 청구는 어디서 해?",
        ),
        claim_channels=(
            claim_channel_block(insurers, has_medical_indemnity=False) if insurers else None
        ),
    )


def _diagnosis_scenario(context: QaContext) -> tuple[str, str] | None:
    category = _diagnosis_category(context.question)
    if category is not None and _is_diagnosis_claim_turn(context.question):
        return context.question, category

    if not any(term in context.question for term in _CLAIM_RELEVANCE_TERMS):
        return None
    for message in reversed(context.history):
        if message.role != "user":
            continue
        category = _diagnosis_category(message.content)
        if category is not None and any(term in message.content for term in _DIAGNOSIS_EVENT_TERMS):
            return f"{message.content}\n{context.question}", category
        break
    return None


def _diagnosis_category(text: str) -> str | None:
    if any(term in text for term in _EXPLICIT_COVERAGE_QUESTION_TERMS):
        return None
    category = classify_coverage(text)
    if category in _DIAGNOSIS_CATEGORIES:
        return category
    compact = "".join(text.split())
    if "암" in compact:
        return CANCER
    return None


def _is_diagnosis_claim_turn(question: str) -> bool:
    return any(term in question for term in _DIAGNOSIS_EVENT_TERMS) or any(
        term in question for term in _CLAIM_RELEVANCE_TERMS
    )


def _diagnosis_evidence(
    catalog: EvidenceCatalog,
    scenario_text: str,
    category: str,
) -> tuple[ConsultationEvidence, ...]:
    evidence = tuple(
        catalog.by_id[evidence_id]
        for evidence_id in catalog.coverage_ids_by_category.get(category, ())
        if evidence_id in catalog.by_id
    )
    if category != CANCER or "유사암" in scenario_text:
        return evidence

    primary = tuple(
        item
        for item in evidence
        if item.coverage_name is not None
        and not any(
            term in _base_coverage_name(item.coverage_name)
            for term in _SECONDARY_CANCER_COVERAGE_TERMS
        )
    )
    return primary or evidence


def _diagnosis_evidence_insurers(
    context: QaContext,
    evidence: tuple[ConsultationEvidence, ...],
) -> list[str]:
    coverage_names = {item.coverage_name for item in evidence if item.coverage_name is not None}
    insurers: list[str] = []
    for total in context.facts.coverage_summary.totals:
        if total.display_name not in coverage_names:
            continue
        insurers.extend(source.insurer for source in total.composition if source.insurer)
    return list(dict.fromkeys(insurers))


def _answer_policy_terms_question(
    context: QaContext,
    *,
    complete: JsonCompleter | None,
    pass_complete: bool,
    retrieve_policy: PolicyContextRetriever,
    generate_policy: PolicyAnswerGenerator,
) -> PortfolioQuestionResponse:
    missing_terms = _missing_policy_terms_response(context)
    policy_catalog = _policy_session_catalog(
        context.catalog,
        context.policies,
        context.question,
        retrieve_policy,
    )
    if policy_catalog is None:
        return missing_terms

    if pass_complete:
        result = generate_policy(
            context.question,
            policy_catalog.items,
            complete=complete,
        )
    else:
        result = generate_policy(context.question, policy_catalog.items)
    return _policy_generation_response(result, policy_catalog, missing_terms)


def _missing_policy_terms_response(context: QaContext) -> PortfolioQuestionResponse:
    matching_evidence = [
        item
        for item in context.catalog.items
        if item.coverage_name is not None
        and query_contains_canonical_name(
            context.question,
            _base_coverage_name(item.coverage_name),
        )
    ]
    if matching_evidence:
        answer = (
            "질문하신 담보는 가입된 것으로 확인돼요. 다만 **정확한 지급 조건은 "
            "지금 자료만으로 확인할 수 없어요.**\n\n"
            "지급사유·면책·감액 조건은 가입한 상품의 약관 원문을 함께 봐야 해요."
        )
    else:
        answer = (
            "지금 올려주신 자료에서는 질문한 담보와 약관 근거를 찾지 못했어요.\n\n"
            "담보명과 가입 상품의 약관 원문이 함께 확인되면 지급 조건을 살펴볼 수 있어요."
        )

    return PortfolioQuestionResponse(
        status="no_data",
        answer=answer,
        citations=[citation_from_evidence(item) for item in matching_evidence],
        limitations=standard_limitations(context.facts),
        suggestions=question_suggestions("가입한 보험과 담보 목록을 다시 보여줘?"),
    )


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
            "실손의료비 청구는 어디서 해?",
        ]
    if any(
        item.is_medical_indemnity for item in context.facts.coverage_summary.actual_loss_coverages
    ):
        candidates.append("실손의료비 청구는 어디서 해?")
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
    if summary.actual_loss_coverages:
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


def _has_any_uploaded_policy_data(context: QaContext) -> bool:
    return bool(
        context.facts.policies
        or context.auto_policies
        or context.facts.coverage_summary.damage_coverages
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
        answer=f"가입하신 상품의 약관에서 확인한 내용이에요.\n\n{result.answer.strip()}",
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
        answer=f"먼저 일반적인 확인 기준부터 말씀드릴게요.\n\n{result.answer.strip()}",
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
    policies: list[PolicyInput],
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
) -> PortfolioQuestionResponse:
    labels: list[str] = []
    evidence_ids: list[str] = []
    evidence_by_policy_id = {
        item.policy_id: item.id
        for item in catalog.items
        if item.policy_id is not None
        and (
            item.id.startswith("policy:")
            or item.id.startswith("auto:")
            or item.id.startswith("damage:")
        )
    }
    for policy in policies:
        insurer = policy.기본정보.보험사 or "보험사 미확인"
        product = policy.기본정보.상품명 or "상품명 미확인"
        classification = policy.기본정보.보험분류 or "미분류"
        labels.append(f"{insurer} · {product} ({classification})")
        if policy.id is not None:
            evidence_id = evidence_by_policy_id.get(policy.id)
            if evidence_id is not None:
                evidence_ids.append(evidence_id)

    items = "\n".join(f"- {label}" for label in labels)
    content = f"올려주신 증권을 모두 확인해보니 보험은 **{len(labels)}건**이에요.\n\n{items}"
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
            or query_contains_canonical_name(
                question,
                canonicalize_coverage_name(_base_coverage_name(total.display_name)).normalized_key,
            )
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
        damage_response = _answer_damage_coverage_lookup(question, facts, catalog)
        if damage_response is not None:
            return damage_response
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


def _answer_coverage_lookup(
    question: str,
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
) -> PortfolioQuestionResponse | None:
    if any(term in question for term in _EXPLICIT_ACTUAL_LOSS_LOOKUP_TERMS):
        return _answer_actual_loss_lookup(facts, catalog)
    if any(term in question for term in _MEDICAL_INDEMNITY_LOOKUP_TERMS):
        return _answer_medical_indemnity_lookup(facts, catalog)
    if any(term in question for term in _ACTUAL_LOSS_LOOKUP_TERMS):
        return _answer_actual_loss_lookup(facts, catalog)
    return _answer_damage_coverage_lookup(question, facts, catalog)


def _answer_adequacy_lookup(
    question: str,
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
) -> PortfolioQuestionResponse | None:
    target = _essential_target_kind(question)
    if target is None:
        return None
    item = next(
        (
            candidate
            for candidate in facts.coverage_summary.essential_coverage_check.items
            if candidate.kind == target
        ),
        None,
    )
    if item is None:
        return None

    confirmed = _format_confirmed_amount(item.confirmed_amount)
    reference = _format_reference_range(item.reference_min_amount, item.reference_max_amount)
    lines = [item.detail]
    if confirmed is not None:
        lines.append(f"현재 확인된 금액은 **{confirmed}**이에요.")
    if reference is not None:
        lines.append(f"일반 점검용 참고 범위는 **{reference}**로 보고 있어요.")
    lines.append("다만 적정 금액은 소득, 부양가족, 치료 중 생활비 필요액에 따라 달라져요.")

    sections = [
        AnswerSection(
            title="현재 확인된 보장",
            content="\n".join(f"- {line}" for line in lines),
            basis="general_guidance",
        )
    ]
    evidence_ids = _evidence_ids_for_coverage_names(item.matched_coverage_names, catalog)
    return PortfolioQuestionResponse(
        status="answered",
        answer="\n\n".join(
            _markdown_section(section.title, section.content) for section in sections
        ),
        sections=sections,
        citations=[
            citation_from_evidence(catalog.by_id[evidence_id])
            for evidence_id in evidence_ids
            if evidence_id in catalog.by_id
        ],
        limitations=standard_limitations(facts)
        + ["참고 범위는 공식 기준이 아니라 보장 점검을 위한 일반 가이드입니다."],
        suggestions=_fact_suggestions(facts),
    )


def _answer_medical_indemnity_lookup(
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
) -> PortfolioQuestionResponse:
    medical_coverages = [
        item for item in facts.coverage_summary.actual_loss_coverages if item.is_medical_indemnity
    ]
    if medical_coverages:
        evidence_ids = [
            f"actual-loss:{index}"
            for index, item in enumerate(
                facts.coverage_summary.actual_loss_coverages,
                start=1,
            )
            if item.is_medical_indemnity
        ]
        names = [
            " · ".join(
                value for value in (item.insurer, item.product_name, item.coverage_name) if value
            )
            for item in medical_coverages
        ]
        content = "실손의료보험 관련 담보가 확인돼요.\n\n" + "\n".join(
            f"- {name}" for name in names
        )
        return _fact_response(content, evidence_ids, catalog, facts)

    gap_ids = [
        item.id
        for item in catalog.items
        if item.id.startswith("gap:") and item.coverage_name == "실손의료비"
    ]
    content = "현재 업로드된 증권에서는 **실손의료보험 담보를 확인하지 못했어요.**"
    return _fact_response(content, gap_ids, catalog, facts)


def _answer_actual_loss_lookup(
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
) -> PortfolioQuestionResponse:
    actual_loss_coverages = facts.coverage_summary.actual_loss_coverages
    if not actual_loss_coverages:
        content = "현재 업로드된 증권에서는 **실손형 담보를 확인하지 못했어요.**"
        return _fact_response(content, [], catalog, facts)

    coverage_by_identity: dict[tuple[str, str], ActualLossCoverageItem] = {}
    for coverage in actual_loss_coverages:
        key = (
            coverage.normalized_name or coverage.coverage_name,
            coverage.coverage_domain,
        )
        coverage_by_identity.setdefault(key, coverage)

    lines = []
    for coverage in coverage_by_identity.values():
        domain = _actual_loss_domain_label(coverage.coverage_domain)
        duplicate = " · 여러 계약에서 확인" if coverage.duplicate_across_contracts else ""
        lines.append(f"- {coverage.coverage_name} ({domain}{duplicate})")
    content = (
        "실손형은 실제 발생한 손해를 약관 범위에서 보상하는 지급 방식이에요. "
        "실손의료보험은 그중 의료비 영역이에요.\n\n" + "\n".join(lines)
    )
    evidence_ids = _actual_loss_evidence_ids(actual_loss_coverages, catalog)
    return _fact_response(content, evidence_ids, catalog, facts)


def _actual_loss_evidence_ids(
    coverages: list[ActualLossCoverageItem],
    catalog: EvidenceCatalog,
) -> list[str]:
    evidence_ids: list[str] = []
    for coverage in coverages:
        prefixes = ("damage:", "actual-loss:") if coverage.is_damage_policy else ("actual-loss:",)
        for prefix in prefixes:
            evidence = next(
                (
                    item
                    for item in catalog.items
                    if item.id.startswith(prefix)
                    and item.policy_id == coverage.policy_id
                    and item.insurer == coverage.insurer
                    and item.product_name == coverage.product_name
                    and item.coverage_name == coverage.coverage_name
                ),
                None,
            )
            if evidence is not None:
                evidence_ids.append(evidence.id)
                break
    return list(dict.fromkeys(evidence_ids))


def _actual_loss_domain_label(domain: str) -> str:
    return {
        "medical_expense": "실손의료비",
        "travel_medical_expense": "여행 의료비 실손형",
        "legal_cost": "법률 비용 실손형",
        "property_damage": "재산 손해 실손형",
        "liability": "배상책임 실손형",
        "auto": "자동차 손해 실손형",
        "other": "기타 실손형",
    }.get(domain, "기타 실손형")


def _answer_damage_coverage_lookup(
    question: str,
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
) -> PortfolioQuestionResponse | None:
    matches = [
        item
        for item in catalog.items
        if item.id.startswith("damage:")
        and item.coverage_name is not None
        and query_contains_canonical_name(question, _base_coverage_name(item.coverage_name))
    ]
    if not matches:
        return None

    evidence_ids = [item.id for item in matches]
    content = "질문하신 담보를 찾아보니 이렇게 확인돼요.\n\n" + "\n".join(
        f"- {item.fact}" for item in matches
    )
    return _fact_response(content, evidence_ids, catalog, facts)


def _answer_status(
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
    auto_policies: tuple[PolicyInput, ...] = (),
) -> PortfolioQuestionResponse:
    summary = facts.coverage_summary
    auto_note = f", 자동차보험 {len(auto_policies)}건" if auto_policies else ""
    content = "지금 올려주신 자료의 분석 상태는 이래요.\n\n" + "\n".join(
        [
            f"- 비자동차 보험: **{len(facts.policies)}건**{auto_note}",
            f"- 정액형 합계: **{len(summary.totals)}종**",
            f"- 실손형 담보: **{len(summary.actual_loss_coverages)}건**",
            (
                "- 실손의료비 담보: "
                f"**{sum(item.is_medical_indemnity for item in summary.actual_loss_coverages)}건**"
            ),
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
        answer=content.strip(),
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
    include_medical_indemnity = _claim_question_targets_medical_indemnity(
        question,
        facts.coverage_summary.actual_loss_coverages,
    )
    if include_medical_indemnity:
        insurers = [
            item.insurer
            for item in facts.coverage_summary.actual_loss_coverages
            if item.is_medical_indemnity and item.insurer
        ]
    insurers = list(dict.fromkeys(insurers))
    block = claim_channel_block(
        insurers,
        has_medical_indemnity=(
            include_medical_indemnity
            and any(
                item.is_medical_indemnity for item in facts.coverage_summary.actual_loss_coverages
            )
        ),
    )
    medical_lead = ""
    if include_medical_indemnity and insurers:
        medical_lead = (
            f"증권에서 확인된 실손의료보험사는 **{', '.join(insurers)}**예요. "
            "보험사 채널이나 **실손24**에서 청구할 수 있어요.\n\n"
        )
    lead_in = (
        medical_lead + "**청구는 아래 채널에서 확인하실 수 있어요.**\n\n"
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


def _claim_question_targets_medical_indemnity(
    question: str,
    actual_loss_coverages: list[ActualLossCoverageItem],
) -> bool:
    named_coverages = [
        item
        for item in actual_loss_coverages
        if query_contains_canonical_name(question, _base_coverage_name(item.coverage_name))
    ]
    if named_coverages:
        return all(item.is_medical_indemnity for item in named_coverages)
    if any(term in question for term in _EXPLICIT_ACTUAL_LOSS_LOOKUP_TERMS):
        return False
    compact = "".join(question.split())
    return any(term in question for term in _MEDICAL_INDEMNITY_LOOKUP_TERMS) or any(
        term in compact for term in _MEDICAL_INDEMNITY_LOOKUP_TERMS
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


def _is_adequacy_question(question: str) -> bool:
    return any(term in question for term in _ADEQUACY_TERMS)


def _is_generic_amount_definition(context: QaContext) -> bool:
    definition_terms = ("뜻", "의미", "무슨 말", "뭐야", "같은 거")
    if not any(term in context.question for term in definition_terms):
        return False
    return not _question_targets_held_coverage(context)


def _is_actual_loss_rule_question(question: str) -> bool:
    if not any(term in question for term in _MEDICAL_INDEMNITY_LOOKUP_TERMS):
        return False
    return any(
        term in question
        for term in ("여러 개", "여러개", "보험마다", "다 받을", "중복 지급", "비례")
    )


def _requires_policy_terms(question: str) -> bool:
    return any(term in question for term in _POLICY_TERMS_QUESTION_TERMS)


def _question_targets_held_coverage(context: QaContext) -> bool:
    return any(
        item.coverage_name is not None
        and query_contains_canonical_name(
            context.question,
            _base_coverage_name(item.coverage_name),
        )
        for item in context.catalog.items
    )


def _essential_target_kind(question: str) -> str | None:
    if "사망" in question:
        return "death"
    if "암" in question:
        return "cancer"
    if "뇌" in question:
        return "cerebrovascular"
    if "심장" in question or "심질환" in question or "허혈성" in question:
        return "ischemic_heart"
    return None


def _format_confirmed_amount(amount: int | None) -> str | None:
    if amount is None:
        return None
    return f"{amount:,}원"


def _format_reference_range(min_amount: int | None, max_amount: int | None) -> str | None:
    if min_amount is None or max_amount is None:
        return None
    if min_amount == max_amount:
        return f"{min_amount:,}원"
    return f"{min_amount:,}원~{max_amount:,}원"


def _evidence_ids_for_coverage_names(
    coverage_names: list[str],
    catalog: EvidenceCatalog,
) -> list[str]:
    evidence_ids: list[str] = []
    for coverage_name in coverage_names:
        base_name = _base_coverage_name(coverage_name)
        for item in catalog.items:
            if item.coverage_name is None:
                continue
            if query_contains_canonical_name(base_name, _base_coverage_name(item.coverage_name)):
                evidence_ids.append(item.id)
    return list(dict.fromkeys(evidence_ids))


def _base_coverage_name(coverage_name: str) -> str:
    return coverage_name.split("(")[0].strip() or coverage_name


def _markdown_section(title: str, content: str) -> str:
    return f"**{title}**\n\n{content.strip()}"
