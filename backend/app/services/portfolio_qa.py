"""Conversational Q&A grounded in uploaded portfolio facts."""

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
from app.services.coverage_taxonomy import LifeStageCheck, check_life_stage
from app.services.llm import JsonCompleter
from app.services.portfolio_consultation import (
    EvidenceCatalog,
    build_evidence_catalog,
)
from app.services.portfolio_demographics import resolve_portfolio_demographics
from app.services.portfolio_qa_generation import generate_consultation_answer
from app.services.portfolio_summary import (
    PortfolioFacts,
    build_portfolio_facts,
    normalize_coverage_name,
)

_CLAIM_TERMS = (
    "보상되",
    "보상 받을",
    "보상받을",
    "지급 조건",
    "면책",
    "약관",
    "청구",
    "보험금 받을",
    "보험금을 받을",
)
_AMOUNT_TERMS = ("합계", "총액", "얼마", "가입금액")
_STATUS_TERMS = ("추출 상태", "분석 상태", "제외된", "확인 못한")
_HOLDING_TERMS = ("몇 개", "몇개", "몇 건", "몇건", "보유 중", "목록", "가입한 보험")


def answer_portfolio_question(
    question: str,
    policies: list[PolicyInput],
    *,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
    complete: JsonCompleter | None = None,
) -> PortfolioQuestionResponse:
    """Answer with cited facts, or refuse conclusions that require policy terms."""

    insured = resolve_portfolio_demographics(policies, demographics)
    facts = build_portfolio_facts(policies)
    normalized_question = question.strip()
    life_stage_check = _life_stage_check(insured, facts)
    catalog = build_evidence_catalog(facts, insured, life_stage_check.missing)

    if not facts.policies:
        limitations = ["보험증권을 먼저 업로드해 주세요."]
        if facts.coverage_summary.excluded_auto_policy_count:
            limitations.append("자동차 보험은 별도 분석 대상이라 현재 Q&A에서 제외합니다.")
        return _with_demographics(
            PortfolioQuestionResponse(
                status="no_data",
                answer="상담에 사용할 비자동차 보험 정보가 아직 없어요.",
                citations=[],
                limitations=limitations,
                suggestions=["보험증권을 업로드한 뒤 다시 질문해 주세요."],
            ),
            insured,
        )
    if any(term in normalized_question for term in _CLAIM_TERMS):
        return _with_demographics(_refuse_claim_question(), insured)
    if any(term in normalized_question for term in _AMOUNT_TERMS):
        return _with_demographics(_answer_amount(normalized_question, facts, catalog), insured)
    if any(term in normalized_question for term in _STATUS_TERMS):
        return _with_demographics(_answer_status(facts, catalog), insured)
    if any(term in normalized_question for term in _HOLDING_TERMS):
        return _with_demographics(_answer_holdings(facts, catalog), insured)

    fallback = _consultation_fallback(facts, insured, life_stage_check, catalog)
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


def _answer_holdings(facts: PortfolioFacts, catalog: EvidenceCatalog) -> PortfolioQuestionResponse:
    labels: list[str] = []
    evidence_ids: list[str] = []
    policy_evidence = [item for item in catalog.items if item.id.startswith("policy:")]
    for policy, evidence in zip(facts.policies, policy_evidence, strict=True):
        insurer = policy.기본정보.보험사 or "보험사 미확인"
        product = policy.기본정보.상품명 or "상품명 미확인"
        classification = policy.기본정보.보험분류 or "미분류"
        labels.append(f"{insurer} {product}({classification})")
        evidence_ids.append(evidence.id)
    content = f"업로드된 비자동차 보험은 {len(labels)}건이에요: {', '.join(labels)}."
    return _fact_response(content, evidence_ids, catalog, facts)


def _answer_amount(
    question: str, facts: PortfolioFacts, catalog: EvidenceCatalog
) -> PortfolioQuestionResponse:
    selected_totals = facts.coverage_summary.totals
    if not _is_overall_amount_question(question):
        normalized_question = normalize_coverage_name(question)
        matches = [
            total
            for total in facts.coverage_summary.totals
            if total.normalized_name in normalized_question
        ]
        matches.sort(key=lambda total: len(total.normalized_name), reverse=True)
        selected_totals = matches[:1]

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
        and normalize_coverage_name(evidence.coverage_name) in selected_names
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


def _answer_status(facts: PortfolioFacts, catalog: EvidenceCatalog) -> PortfolioQuestionResponse:
    summary = facts.coverage_summary
    content = (
        f"보험 {len(facts.policies)}건에서 정액형 합계 {len(summary.totals)}종을 확인했고, "
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
            "상담에서 함께 점검해 보세요."
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
        AnswerSection(title="상담 전 검토 제안", content=guidance, basis="general_guidance"),
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
            "상담 전에 준비할 정보는 무엇인가요?",
        ],
    )


def _refuse_claim_question() -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="refused",
        answer=(
            "그 판단은 담보명과 가입금액만으로는 정확히 답할 수 없어요. "
            "해당 약관의 보장 조건·면책·지급 사유를 확인해야 합니다."
        ),
        citations=[],
        limitations=[
            "현재는 업로드된 증권의 구조화 정보만 사용하며 약관 RAG는 아직 연결되지 않았습니다."
        ],
        suggestions=["가입한 담보와 금액처럼 증권에서 확인 가능한 내용을 물어보세요."],
    )


def _standard_limitations(facts: PortfolioFacts) -> list[str]:
    summary = facts.coverage_summary
    limitations = ["보상 조건·면책·지급 가능성은 약관 근거 없이 판단하지 않습니다."]
    if summary.indemnity_coverages:
        limitations.append("실손형 담보는 가입금액 합계에 포함하지 않았습니다.")
    if summary.excluded_coverages:
        limitations.append("지급유형 또는 금액이 확인되지 않은 담보는 합계에 포함하지 않았습니다.")
    if summary.excluded_auto_policy_count:
        limitations.append("자동차 보험은 별도 분석 대상이라 현재 답변에서 제외했습니다.")
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


def _with_demographics(
    response: PortfolioQuestionResponse,
    demographics: InsuredDemographics,
) -> PortfolioQuestionResponse:
    limitations = list(response.limitations)
    demographic_notice = {
        "conflict": "증권별 피보험자 정보가 서로 달라 나이·성별 개인화를 적용하지 않았습니다.",
        "conflict_user_override": (
            "증권별 피보험자 정보가 서로 달라 사용자가 확인한 정보로 개인화했습니다."
        ),
        "missing": "증권에서 피보험자 나이·성별을 확인하지 못해 개인화를 적용하지 않았습니다.",
    }.get(demographics.status)
    if demographic_notice and demographic_notice not in limitations:
        limitations.append(demographic_notice)
    return response.model_copy(update={"demographics": demographics, "limitations": limitations})
