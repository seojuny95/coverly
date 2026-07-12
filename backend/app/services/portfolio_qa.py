"""Conversational Q&A grounded in uploaded portfolio facts."""

from collections.abc import Callable, Iterator

from app.schemas.consultation import (
    AnswerSection,
    ConsultationEvidence,
    InsuredDemographics,
)
from app.schemas.portfolio import PolicyInput
from app.schemas.qa import (
    AnswerCitation,
    ConversationMessage,
    PortfolioQuestionResponse,
)
from app.services.claim_channels import claim_channel_block
from app.services.coverage_name_matching import (
    canonicalize_coverage_name,
    query_contains_canonical_name,
)
from app.services.coverage_taxonomy import LifeStageCheck, check_life_stage
from app.services.llm import JsonCompleter, TextStreamer
from app.services.portfolio_consultation import (
    EvidenceCatalog,
    build_evidence_catalog,
    with_session_evidence,
)
from app.services.portfolio_demographics import resolve_portfolio_demographics
from app.services.portfolio_qa_generation import (
    QaStreamEvent,
    generate_consultation_answer,
    stream_consultation_answer,
)
from app.services.portfolio_summary import (
    PortfolioFacts,
    build_portfolio_facts,
    is_auto_policy,
)
from app.services.rag.answer import RagAnswer, RagCitation, answer_official_question
from app.services.session_rag import retrieve_policy_context

# "How do I claim?" is procedural — answer with the deterministic channel directory.
_CLAIM_HOWTO_TERMS = ("청구", "신청", "접수", "서류")
# A claim-how-to question is auto-related only when it names a car-accident context;
# otherwise auto insurers stay out of a health/life claim answer.
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

OfficialAnswerer = Callable[[str], RagAnswer]


def answer_portfolio_question(
    question: str,
    policies: list[PolicyInput],
    *,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
    complete: JsonCompleter | None = None,
    official_answer: OfficialAnswerer | None = None,
) -> PortfolioQuestionResponse:
    """Answer with cited facts, or refuse conclusions that require policy terms."""

    insured = resolve_portfolio_demographics(policies, demographics)
    facts = build_portfolio_facts(policies)
    auto_policies = tuple(policy for policy in policies if is_auto_policy(policy))
    normalized_question = question.strip()
    life_stage_check = _life_stage_check(insured, facts)
    catalog = build_evidence_catalog(facts, insured, life_stage_check.missing, auto_policies)

    official_response = None
    if complete is None or official_answer is not None:
        official_response = _answer_with_official_rag(normalized_question, official_answer)
    if official_response is not None:
        return _with_demographics(official_response, insured)

    if not facts.policies and not auto_policies:
        return _with_demographics(_no_uploaded_policies_response(), insured)
    if any(term in normalized_question for term in _AMOUNT_TERMS):
        return _with_demographics(_answer_amount(normalized_question, facts, catalog), insured)
    if any(term in normalized_question for term in _STATUS_TERMS):
        return _with_demographics(_answer_status(facts, catalog, auto_policies), insured)
    if any(term in normalized_question for term in _HOLDING_TERMS):
        return _with_demographics(_answer_holdings(facts, catalog, auto_policies), insured)
    if any(term in normalized_question for term in _CLAIM_HOWTO_TERMS):
        channels = _answer_claim_channels(policies, facts, normalized_question)
        return _with_demographics(channels, insured)

    fallback = _consultation_fallback(facts, insured, life_stage_check, catalog)
    catalog = _with_session_context(catalog, policies, normalized_question)
    response = generate_consultation_answer(
        fallback=fallback,
        question=normalized_question,
        demographics=insured,
        history=history or [],
        life_stage_check=life_stage_check,
        catalog=catalog,
        standard_limitations=_standard_limitations(facts),
        complete=complete,
    )
    return _with_demographics(response, insured)


def _no_uploaded_policies_response() -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="no_data",
        answer="살펴볼 보험 정보가 아직 없어요.",
        citations=[],
        limitations=["보험증권을 먼저 업로드해 주세요."],
        suggestions=["보험증권을 업로드한 뒤 다시 질문해 주세요."],
    )


def _stream_response(response: PortfolioQuestionResponse) -> Iterator[QaStreamEvent]:
    """Emit a fully-computed deterministic answer as a single-delta stream."""

    yield {"type": "meta", "status": response.status, "generation": response.generation}
    yield {"type": "delta", "text": response.answer}
    yield {
        "type": "end",
        "status": response.status,
        "generation": response.generation,
        "citations": [citation.model_dump(mode="json") for citation in response.citations],
        "limitations": response.limitations,
        "suggestions": response.suggestions,
        "claim_channels": (
            response.claim_channels.model_dump(mode="json") if response.claim_channels else None
        ),
    }


def stream_portfolio_answer(
    question: str,
    policies: list[PolicyInput],
    *,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
    stream: TextStreamer | None = None,
    official_answer: OfficialAnswerer | None = None,
) -> Iterator[QaStreamEvent]:
    """Stream the answer: deterministic routes emit at once, the LLM route streams."""

    insured = resolve_portfolio_demographics(policies, demographics)
    facts = build_portfolio_facts(policies)
    auto_policies = tuple(policy for policy in policies if is_auto_policy(policy))
    normalized_question = question.strip()
    life_stage_check = _life_stage_check(insured, facts)
    catalog = build_evidence_catalog(facts, insured, life_stage_check.missing, auto_policies)

    official_response = None
    if stream is None or official_answer is not None:
        official_response = _answer_with_official_rag(normalized_question, official_answer)
    if official_response is not None:
        yield from _stream_response(_with_demographics(official_response, insured))
        return

    if not facts.policies and not auto_policies:
        yield from _stream_response(_with_demographics(_no_uploaded_policies_response(), insured))
        return
    if any(term in normalized_question for term in _AMOUNT_TERMS):
        response = _answer_amount(normalized_question, facts, catalog)
        yield from _stream_response(_with_demographics(response, insured))
        return
    if any(term in normalized_question for term in _STATUS_TERMS):
        status = _answer_status(facts, catalog, auto_policies)
        yield from _stream_response(_with_demographics(status, insured))
        return
    if any(term in normalized_question for term in _HOLDING_TERMS):
        holdings = _answer_holdings(facts, catalog, auto_policies)
        yield from _stream_response(_with_demographics(holdings, insured))
        return
    if any(term in normalized_question for term in _CLAIM_HOWTO_TERMS):
        channels = _answer_claim_channels(policies, facts, normalized_question)
        yield from _stream_response(_with_demographics(channels, insured))
        return

    fallback = _with_demographics(
        _consultation_fallback(facts, insured, life_stage_check, catalog), insured
    )
    catalog = _with_session_context(catalog, policies, normalized_question)
    limitations = list(_standard_limitations(facts))
    notice = _demographic_notice(insured)
    if notice:
        limitations.append(notice)
    yield from stream_consultation_answer(
        question=normalized_question,
        demographics=insured,
        history=history or [],
        life_stage_check=life_stage_check,
        catalog=catalog,
        limitations=limitations,
        suggestions=["다른 담보나 보장 공백도 이어서 물어보세요."],
        fallback=fallback,
        claim_targets=_claim_targets(policies, _medical_indemnity_names(facts)),
        stream=stream,
    )


def _claim_targets(
    policies: list[PolicyInput], medical_indemnity_names: set[str]
) -> list[tuple[str, str, bool]]:
    """Map each held coverage to its policy's insurer for claim-channel routing.

    Covers every policy including auto, so an accident answer that names an auto
    coverage (대물배상 등) resolves to the auto insurer. Uses the coverage's base
    name (dropping a "(유사암제외)"-style suffix) so a conversational mention like
    "암 진단비" still resolves to 암진단비(유사암제외); the insurer comes from the
    policy — never None like a multi-policy total.
    """

    targets: list[tuple[str, str, bool]] = []
    for policy in policies:
        insurer = policy.기본정보.보험사
        if not insurer:
            continue
        for coverage in policy.보장목록:
            base_name = coverage.담보명.split("(")[0].strip() or coverage.담보명
            normalized = canonicalize_coverage_name(base_name).normalized_key
            if not normalized:
                continue
            # 실손24 belongs to non-auto medical indemnity (실손/실비/비례) only — use
            # the shared classifier's result, not a brittle 지급유형 == "실손" match.
            targets.append((normalized, insurer, normalized in medical_indemnity_names))
    return targets


def _with_session_context(
    catalog: EvidenceCatalog,
    policies: list[PolicyInput],
    question: str,
) -> EvidenceCatalog:
    session_ids = [policy.문서세션ID for policy in policies if policy.문서세션ID is not None]
    if not session_ids:
        return catalog
    return with_session_evidence(catalog, retrieve_policy_context(session_ids, question))


def _answer_with_official_rag(
    question: str,
    answerer: OfficialAnswerer | None,
) -> PortfolioQuestionResponse | None:
    if not _should_try_official_rag(question):
        return None
    result = (answerer or answer_official_question)(question)
    if result.status != "answered":
        return None

    section = AnswerSection(
        title="공식자료 기준 일반 안내",
        content=result.answer,
        basis="general_guidance",
    )
    return PortfolioQuestionResponse(
        status="answered",
        answer=result.answer,
        sections=[section],
        citations=[_official_citation(citation) for citation in result.citations],
        limitations=list(result.limitations),
        suggestions=_official_suggestions(result),
        generation="llm",
    )


def _should_try_official_rag(question: str) -> bool:
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
        return ["가입한 상품의 실제 약관과 보험사 심사 기준을 함께 확인해 주세요."]
    return ["업로드한 증권의 담보명이나 보장내용과 함께 다시 물어보세요."]


def _medical_indemnity_names(facts: PortfolioFacts) -> set[str]:
    return {
        canonicalize_coverage_name(item.coverage_name).normalized_key
        for item in facts.coverage_summary.indemnity_coverages
    }


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

    content = f"업로드된 보험은 {len(labels)}건이에요: {', '.join(labels)}."
    return _fact_response(content, evidence_ids, catalog, facts)


def _answer_amount(
    question: str, facts: PortfolioFacts, catalog: EvidenceCatalog
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
                    "질문과 일치하는 담보가 여러 개라 하나의 가입금액으로 답하기 어려워요. "
                    "증권에 적힌 담보명 하나를 지정해 주세요."
                ),
                citations=[],
                limitations=_standard_limitations(facts),
                suggestions=["확인할 담보명 하나와 함께 가입금액을 질문해 주세요."],
            )
        selected_totals = matches

    if not selected_totals:
        return PortfolioQuestionResponse(
            status="no_data",
            answer="올린 증권에서 질문한 담보의 확인 가능한 가입금액을 찾지 못했습니다.",
            citations=[],
            limitations=_standard_limitations(facts),
            suggestions=["담보명을 증권에 적힌 표현으로 다시 질문해 보세요."],
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
            f"{selected_totals[0].display_name}의 확인 가능한 가입금액 합계는 "
            f"{total_amount:,}원이에요."
        )
    else:
        content = (
            f"확인 가능한 정액형 담보 {len(selected_totals)}종의 가입금액 합계는 "
            f"{total_amount:,}원이에요."
        )
    return _fact_response(content, evidence_ids, catalog, facts)


def _answer_status(
    facts: PortfolioFacts,
    catalog: EvidenceCatalog,
    auto_policies: tuple[PolicyInput, ...] = (),
) -> PortfolioQuestionResponse:
    summary = facts.coverage_summary
    auto_note = f", 자동차보험 {len(auto_policies)}건" if auto_policies else ""
    content = (
        f"비자동차 보험 {len(facts.policies)}건{auto_note}에서 "
        f"정액형 합계 {len(summary.totals)}종을 확인했고, "
        f"실손형 {len(summary.indemnity_coverages)}건과 "
        f"합계 제외 {len(summary.excluded_coverages)}건이 있어요."
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
        answer=content,
        sections=[section],
        citations=[
            _citation(catalog.by_id[evidence_id])
            for evidence_id in dict.fromkeys(evidence_ids)
            if evidence_id in catalog.by_id
        ],
        limitations=_standard_limitations(facts),
        suggestions=["다른 담보나 보장 공백도 이어서 물어보세요."],
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
        answer="\n\n".join(f"{section.title}\n{section.content}" for section in sections),
        sections=sections,
        citations=[
            _citation(catalog.by_id[evidence_id])
            for evidence_id in dict.fromkeys(evidence_ids)
            if evidence_id in catalog.by_id
        ],
        limitations=_standard_limitations(facts)
        + ["AI 상담 답변을 사용할 수 없어 확인된 사실 기반 안내를 표시합니다."],
        suggestions=[
            "현재 보장에서 먼저 확인할 항목은 무엇인가요?",
            "다음으로 확인하면 좋은 정보는 무엇인가요?",
        ],
    )


def _answer_claim_channels(
    policies: list[PolicyInput], facts: PortfolioFacts, question: str
) -> PortfolioQuestionResponse:
    auto_related = any(term in question for term in _AUTO_CLAIM_TERMS)
    relevant = policies if auto_related else [p for p in policies if not is_auto_policy(p)]
    insurers = [policy.기본정보.보험사 for policy in relevant if policy.기본정보.보험사]
    # 실손24 is medical-indemnity only — keyed off the non-auto classifier, not auto 비례.
    has_indemnity = bool(facts.coverage_summary.indemnity_coverages)
    block = claim_channel_block(insurers, has_indemnity=has_indemnity)
    lead_in = "청구는 아래 채널에서 확인하실 수 있어요."
    return PortfolioQuestionResponse(
        status="answered",
        answer=lead_in,
        sections=[AnswerSection(title="청구 방법 안내", content=lead_in, basis="general_guidance")],
        citations=[],
        limitations=[
            "청구 방법만 안내했어요. "
            "보상 가능 여부와 지급액은 약관·보험사 안내를 확인해야 정확합니다."
        ],
        suggestions=["가입한 담보와 금액처럼 증권에서 확인 가능한 내용도 물어보세요."],
        claim_channels=block,
    )


def _standard_limitations(facts: PortfolioFacts) -> list[str]:
    summary = facts.coverage_summary
    limitations = ["보상 조건·면책·지급 가능성은 약관 근거 없이 판단하지 않습니다."]
    if summary.indemnity_coverages:
        limitations.append("실손형 담보는 가입금액 합계에 포함하지 않았습니다.")
    if summary.excluded_coverages:
        limitations.append("지급유형 또는 금액이 확인되지 않은 담보는 합계에 포함하지 않았습니다.")
    if summary.excluded_auto_policy_count:
        limitations.append("가입금액 합계·집계에는 자동차 보험을 포함하지 않았어요.")
    return limitations


def _life_stage_check(demographics: InsuredDemographics, facts: PortfolioFacts) -> LifeStageCheck:
    if demographics.age is None:
        return LifeStageCheck(life_stage="미상", held=(), missing=())
    coverage_names = [coverage.담보명 for policy in facts.policies for coverage in policy.보장목록]
    return check_life_stage(demographics.age, coverage_names)


def _is_overall_amount_question(question: str) -> bool:
    return any(term in question for term in ("전체", "총합", "모든", "총액"))


def _citation(item: ConsultationEvidence) -> AnswerCitation:
    return AnswerCitation(
        evidence_id=item.id,
        policy_id=item.policy_id,
        insurer=item.insurer,
        product_name=item.product_name,
        coverage_name=item.coverage_name,
    )


def _demographic_notice(demographics: InsuredDemographics) -> str | None:
    return {
        "conflict": "증권별 피보험자 정보가 서로 달라 나이·성별 개인화를 적용하지 않았습니다.",
        "conflict_user_override": (
            "증권별 피보험자 정보가 서로 달라 사용자가 확인한 정보로 개인화했습니다."
        ),
        "missing": "증권에서 피보험자 나이·성별을 확인하지 못해 개인화를 적용하지 않았습니다.",
    }.get(demographics.status)


def _with_demographics(
    response: PortfolioQuestionResponse,
    demographics: InsuredDemographics,
) -> PortfolioQuestionResponse:
    limitations = list(response.limitations)
    demographic_notice = _demographic_notice(demographics)
    if demographic_notice and demographic_notice not in limitations:
        limitations.append(demographic_notice)
    return response.model_copy(update={"demographics": demographics, "limitations": limitations})
