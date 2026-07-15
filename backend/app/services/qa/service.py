"""Conversational Q&A grounded in uploaded portfolio facts."""

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.schemas.consultation import (
    AnswerSection,
    GenerationMode,
    InsuredDemographics,
)
from app.schemas.portfolio import PolicyInput
from app.schemas.qa import (
    AnswerCitation,
    ConversationMessage,
    PortfolioQuestionResponse,
)
from app.services.coverage_knowledge.matching import (
    canonicalize_coverage_name,
    query_contains_canonical_name,
)
from app.services.coverage_knowledge.taxonomy import LifeStageCheck, check_life_stage
from app.services.evidence.catalog import (
    EvidenceCatalog,
    build_evidence_catalog,
    citation_from_evidence,
    with_session_evidence,
)
from app.services.llm import JsonCompleter, TextStreamer
from app.services.portfolio.demographics import resolve_portfolio_demographics
from app.services.portfolio.summary import (
    PortfolioFacts,
    build_portfolio_facts,
    is_auto_policy,
)
from app.services.qa.claim_channels import claim_channel_block
from app.services.qa.generation import (
    QaStreamEvent,
    generate_consultation_answer,
    stream_consultation_answer,
)
from app.services.qa.planning import PlannedQuestion, QuestionPlan, plan_questions
from app.services.rag.official.answer import RagAnswer, RagCitation, answer_official_question
from app.services.rag.policy import (
    PolicyGenerationResult,
    generate_policy_answer,
    retrieve_policy_context,
)

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
_MAX_SUGGESTIONS = 3
_GREETING_ANSWER = "**안녕하세요.** 가입한 보험과 보장에 관해 궁금한 내용을 물어봐 주세요."
_OUT_OF_SCOPE_ANSWER = (
    "**보험과 관련 없는 정보**는 답변하기 어려워요.\n\n"
    "- 가입 보험, 보장, 약관, 청구와 관련된 질문은 도와드릴 수 있어요."
)

OfficialAnswerer = Callable[[str], RagAnswer]


@dataclass(frozen=True)
class _QaContext:
    question: str
    policies: list[PolicyInput]
    history: list[ConversationMessage]
    insured: InsuredDemographics
    facts: PortfolioFacts
    auto_policies: tuple[PolicyInput, ...]
    life_stage_check: LifeStageCheck
    catalog: EvidenceCatalog


@dataclass(frozen=True)
class _QuestionTurn:
    question: str
    history: list[ConversationMessage]
    plan: QuestionPlan | None


def _markdown_section(title: str, content: str) -> str:
    return f"**{title}**\n\n{content.strip()}"


def answer_portfolio_question(
    question: str,
    policies: list[PolicyInput],
    *,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
    complete: JsonCompleter | None = None,
    official_answer: OfficialAnswerer | None = None,
    plan: JsonCompleter | None = None,
) -> PortfolioQuestionResponse:
    """Answer with cited facts, or refuse conclusions that require policy terms."""

    turn = _plan_question_turn(question, history, plan)
    if turn.plan is not None:
        if turn.plan.clarification is not None:
            return _clarification_response(turn.plan.clarification)
        if _is_scope_only_plan(turn.plan):
            return _answer_scope_only_plan(turn.plan)
        context = _build_qa_context(turn.question, policies, demographics, turn.history)
        return _answer_question_plan(context, turn.plan, complete, official_answer)

    context = _build_qa_context(turn.question, policies, demographics, turn.history)
    return _answer_context(context, complete, official_answer)


def _answer_context(
    context: _QaContext,
    complete: JsonCompleter | None,
    official_answer: OfficialAnswerer | None,
) -> PortfolioQuestionResponse:
    response = _resolve_precomputed_answer(
        context,
        try_official=complete is None or official_answer is not None,
        official_answer=official_answer,
        complete=complete,
        pass_complete=True,
    )
    if response is not None:
        return response

    fallback = _context_fallback(context)

    response = generate_consultation_answer(
        fallback=fallback,
        question=context.question,
        demographics=context.insured,
        history=context.history,
        life_stage_check=context.life_stage_check,
        catalog=context.catalog,
        standard_limitations=_standard_limitations(context.facts),
        complete=complete,
    )
    return _with_demographics(response, context.insured)


def _no_uploaded_policies_response() -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="no_data",
        answer="**살펴볼 보험 정보가 아직 없어요.**\n\n- 보험증권을 먼저 업로드해 주세요.",
        citations=[],
        limitations=["보험증권을 먼저 업로드해 주세요."],
        suggestions=["업로드한 증권에서 어떤 보장을 확인할 수 있어?"],
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


def _plan_question_turn(
    question: str,
    history: list[ConversationMessage] | None,
    complete: JsonCompleter | None,
) -> _QuestionTurn:
    normalized_question = question.strip()
    conversation_history = history or []
    return _QuestionTurn(
        question=normalized_question,
        history=conversation_history,
        plan=plan_questions(normalized_question, conversation_history, complete=complete),
    )


def stream_portfolio_answer(
    question: str,
    policies: list[PolicyInput],
    *,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
    stream: TextStreamer | None = None,
    official_answer: OfficialAnswerer | None = None,
    plan: JsonCompleter | None = None,
) -> Iterator[QaStreamEvent]:
    """Stream the answer: deterministic routes emit at once, the LLM route streams."""

    turn = _plan_question_turn(question, history, plan)
    if turn.plan is not None:
        if turn.plan.clarification is not None:
            yield from _stream_clarification(turn.plan.clarification)
            return
        if _is_scope_only_plan(turn.plan):
            yield from _stream_response(_answer_scope_only_plan(turn.plan))
            return
        context = _build_qa_context(turn.question, policies, demographics, turn.history)
        if len(turn.plan.questions) != 1 or turn.plan.questions[0].scope != "insurance":
            response = _answer_question_plan(context, turn.plan, None, official_answer)
            yield from _stream_response(response)
            return
        context = _context_with_question(context, turn.plan.questions[0].resolved)
    else:
        context = _build_qa_context(turn.question, policies, demographics, turn.history)

    yield from _stream_context(context, stream, official_answer)


def _stream_clarification(question: str) -> Iterator[QaStreamEvent]:
    yield {"type": "meta", "status": "clarify", "generation": "fallback"}
    yield {"type": "delta", "text": question}
    yield {
        "type": "end",
        "status": "clarify",
        "generation": "fallback",
        "citations": [],
        "limitations": [],
        "suggestions": [],
        "claim_channels": None,
    }


def _stream_context(
    context: _QaContext,
    stream: TextStreamer | None,
    official_answer: OfficialAnswerer | None,
) -> Iterator[QaStreamEvent]:
    response = _resolve_precomputed_answer(
        context,
        try_official=stream is None or official_answer is not None,
        official_answer=official_answer,
        complete=None,
        pass_complete=False,
    )
    if response is not None:
        yield from _stream_response(response)
        return

    fallback = _with_demographics(_context_fallback(context), context.insured)
    limitations = list(_standard_limitations(context.facts))
    notice = _demographic_notice(context.insured)
    if notice:
        limitations.append(notice)
    yield from stream_consultation_answer(
        question=context.question,
        demographics=context.insured,
        history=context.history,
        life_stage_check=context.life_stage_check,
        catalog=context.catalog,
        limitations=limitations,
        suggestions=_contextual_suggestions(context),
        fallback=fallback,
        claim_targets=_claim_targets(context.policies, _medical_indemnity_names(context.facts)),
        stream=stream,
    )


def _build_qa_context(
    question: str,
    policies: list[PolicyInput],
    demographics: InsuredDemographics | None,
    history: list[ConversationMessage] | None,
) -> _QaContext:
    insured = resolve_portfolio_demographics(policies, demographics)
    facts = build_portfolio_facts(policies)
    auto_policies = tuple(policy for policy in policies if is_auto_policy(policy))
    life_stage_check = _life_stage_check(insured, facts)
    catalog = build_evidence_catalog(facts, insured, life_stage_check.missing, auto_policies)

    return _QaContext(
        question=question.strip(),
        policies=policies,
        history=history or [],
        insured=insured,
        facts=facts,
        auto_policies=auto_policies,
        life_stage_check=life_stage_check,
        catalog=catalog,
    )


def _context_with_question(context: _QaContext, question: str) -> _QaContext:
    return _QaContext(
        question=question.strip(),
        policies=context.policies,
        history=context.history,
        insured=context.insured,
        facts=context.facts,
        auto_policies=context.auto_policies,
        life_stage_check=context.life_stage_check,
        catalog=context.catalog,
    )


def _clarification_response(question: str) -> PortfolioQuestionResponse:
    return PortfolioQuestionResponse(
        status="clarify",
        answer=_markdown_section("확인이 필요해요", question),
        citations=[],
        limitations=[],
        suggestions=[],
    )


def _is_scope_only_plan(question_plan: QuestionPlan) -> bool:
    return all(planned.scope != "insurance" for planned in question_plan.questions)


def _scope_answer(planned: PlannedQuestion) -> tuple[str, bool]:
    if planned.scope == "greeting":
        return _GREETING_ANSWER, True
    return _OUT_OF_SCOPE_ANSWER, False


def _append_planned_answer(
    answers: list[str],
    question_count: int,
    planned: PlannedQuestion,
    answer: str,
) -> None:
    if question_count == 1:
        answers.append(answer)
    else:
        answers.append(f"**{planned.original}**\n\n{answer}")


def _answer_scope_only_plan(question_plan: QuestionPlan) -> PortfolioQuestionResponse:
    answers: list[str] = []
    answered = False
    for planned in question_plan.questions:
        answer, planned_answered = _scope_answer(planned)
        answered = answered or planned_answered
        _append_planned_answer(answers, len(question_plan.questions), planned, answer)

    return PortfolioQuestionResponse(
        status="answered" if answered else "refused",
        answer="\n\n".join(answers),
        citations=[],
        limitations=[],
        suggestions=[],
    )


def _answer_question_plan(
    context: _QaContext,
    question_plan: QuestionPlan,
    complete: JsonCompleter | None,
    official_answer: OfficialAnswerer | None,
) -> PortfolioQuestionResponse:
    if question_plan.clarification is not None:
        return _clarification_response(question_plan.clarification)

    answers: list[str] = []
    citations: list[AnswerCitation] = []
    limitations: list[str] = []
    suggestions: list[str] = []
    answered = False
    generation: GenerationMode = "fallback"
    claim_channels = None
    insurance_answers = _answer_insurance_questions(
        context,
        question_plan,
        complete,
        official_answer,
    )

    for index, planned in enumerate(question_plan.questions):
        if planned.scope == "insurance":
            response = insurance_answers[index]
            answer = response.answer
            answered = answered or response.status == "answered"
            generation = "llm" if response.generation == "llm" else generation
            citations.extend(response.citations)
            limitations.extend(response.limitations)
            suggestions.extend(response.suggestions)
            claim_channels = claim_channels or response.claim_channels
        else:
            answer, planned_answered = _scope_answer(planned)
            answered = answered or planned_answered
        _append_planned_answer(answers, len(question_plan.questions), planned, answer)

    return PortfolioQuestionResponse(
        status="answered" if answered else "refused",
        answer="\n\n".join(answers),
        citations=_unique_citations(citations),
        limitations=list(dict.fromkeys(limitations)),
        suggestions=_question_suggestions(*suggestions, *_contextual_suggestions(context)),
        generation=generation,
        demographics=context.insured,
        claim_channels=claim_channels,
    )


def _answer_insurance_questions(
    context: _QaContext,
    question_plan: QuestionPlan,
    complete: JsonCompleter | None,
    official_answer: OfficialAnswerer | None,
) -> dict[int, PortfolioQuestionResponse]:
    insurance_tasks = [
        (index, planned)
        for index, planned in enumerate(question_plan.questions)
        if planned.scope == "insurance"
    ]
    if not insurance_tasks:
        return {}
    if len(insurance_tasks) == 1:
        index, planned = insurance_tasks[0]
        return {
            index: _answer_context(
                _context_with_question(context, planned.resolved),
                complete,
                official_answer,
            )
        }

    with ThreadPoolExecutor(max_workers=len(insurance_tasks)) as executor:
        futures = {
            index: executor.submit(
                _answer_context,
                _context_with_question(context, planned.resolved),
                complete,
                official_answer,
            )
            for index, planned in insurance_tasks
        }
        return {index: future.result() for index, future in futures.items()}


def _unique_citations(citations: list[AnswerCitation]) -> list[AnswerCitation]:
    unique: list[AnswerCitation] = []
    seen: set[str] = set()
    for citation in citations:
        key = citation.model_dump_json()
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique


def _contextual_suggestions(context: _QaContext) -> list[str]:
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
    return _question_suggestions(*candidates)


def _fact_suggestions(facts: PortfolioFacts) -> list[str]:
    totals = facts.coverage_summary.totals
    if not totals:
        return _question_suggestions("가입한 보험은 몇 개야?", "분석 상태는 어때?")
    coverage_name = totals[0].display_name
    return _question_suggestions(
        f"{coverage_name} 가입금액은 얼마야?",
        f"{coverage_name} 지급 조건은 뭐야?",
        "가입한 보험은 몇 개야?",
    )


def _question_suggestions(*candidates: str) -> list[str]:
    suggestions: list[str] = []
    for candidate in candidates:
        cleaned = " ".join(candidate.split())
        if not cleaned or cleaned in suggestions:
            continue
        if not cleaned.endswith("?"):
            continue
        suggestions.append(cleaned)
        if len(suggestions) == _MAX_SUGGESTIONS:
            break
    return suggestions


def _resolve_precomputed_answer(
    context: _QaContext,
    *,
    try_official: bool,
    official_answer: OfficialAnswerer | None,
    complete: JsonCompleter | None,
    pass_complete: bool,
) -> PortfolioQuestionResponse | None:
    if try_official:
        response = _answer_with_official_rag(context.question, official_answer)
        if response is not None:
            return _with_demographics(response, context.insured)

    if not context.facts.policies and not context.auto_policies:
        return _with_demographics(_no_uploaded_policies_response(), context.insured)
    if any(term in context.question for term in _AMOUNT_TERMS):
        response = _answer_amount(context.question, context.facts, context.catalog)
        return _with_demographics(response, context.insured)
    if any(term in context.question for term in _STATUS_TERMS):
        response = _answer_status(context.facts, context.catalog, context.auto_policies)
        return _with_demographics(response, context.insured)
    if any(term in context.question for term in _HOLDING_TERMS):
        response = _answer_holdings(context.facts, context.catalog, context.auto_policies)
        return _with_demographics(response, context.insured)
    if any(term in context.question for term in _CLAIM_HOWTO_TERMS):
        response = _answer_claim_channels(context.policies, context.facts, context.question)
        return _with_demographics(response, context.insured)

    policy_catalog = _policy_session_catalog(
        context.catalog,
        context.policies,
        context.question,
    )
    if policy_catalog is None:
        return None

    # Policy generation validates a complete structured draft before streaming,
    # so this path is always returned as one finalized response.
    if pass_complete:
        result = generate_policy_answer(
            context.question,
            policy_catalog.items,
            complete=complete,
        )
    else:
        result = generate_policy_answer(context.question, policy_catalog.items)
    response = _policy_generation_response(result, policy_catalog, _context_fallback(context))
    return _with_demographics(response, context.insured)


def _context_fallback(context: _QaContext) -> PortfolioQuestionResponse:
    return _consultation_fallback(
        context.facts,
        context.insured,
        context.life_stage_check,
        context.catalog,
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
            normalized = _base_normalized_key(coverage.담보명)
            if not normalized:
                continue
            # 실손24 belongs to non-auto medical indemnity (실손/실비/비례) only — use
            # the shared classifier's result, not a brittle 지급유형 == "실손" match.
            # Both sides key off the same base name so a "(질병)"-style suffix on the
            # indemnity coverage still matches the medical-indemnity set.
            targets.append((normalized, insurer, normalized in medical_indemnity_names))
    return targets


def _base_normalized_key(coverage_name: str) -> str:
    """Normalize to a coverage's base name, dropping a "(유사암제외)/(질병)"-style
    suffix, so the same coverage keys identically everywhere it is referenced."""

    base_name = coverage_name.split("(")[0].strip() or coverage_name
    return canonicalize_coverage_name(base_name).normalized_key


def _policy_session_catalog(
    catalog: EvidenceCatalog,
    policies: list[PolicyInput],
    question: str,
) -> EvidenceCatalog | None:
    session_ids = [policy.문서세션ID for policy in policies if policy.문서세션ID is not None]
    if not session_ids:
        return None
    try:
        hits = retrieve_policy_context(session_ids, question)
    except Exception:
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
    answerer: OfficialAnswerer | None,
) -> PortfolioQuestionResponse | None:
    if not _should_try_official_rag(question):
        return None
    try:
        result = (answerer or answer_official_question)(question)
    except Exception:
        # official RAG is a shortcut, not a requirement — a pgvector/OpenAI
        # outage should fall through to the portfolio-fact answer below,
        # not fail the whole question.
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
        return _question_suggestions("내 증권 기준으로도 보상 조건을 확인할 수 있어?")
    return _question_suggestions(
        "이 약관 내용이 내 증권에도 들어 있어?",
        "내 담보의 지급 조건은 뭐야?",
    )


def _medical_indemnity_names(facts: PortfolioFacts) -> set[str]:
    return {
        _base_normalized_key(item.coverage_name)
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

    items = "\n".join(f"- {label}" for label in labels)
    content = f"업로드된 보험은 **{len(labels)}건**이에요.\n\n{items}"
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
                    "**질문과 일치하는 담보가 여러 개**라 하나의 가입금액으로 답하기 어려워요.\n\n"
                    "- 증권에 적힌 담보명 하나를 지정해 주세요."
                ),
                citations=[],
                limitations=_standard_limitations(facts),
                suggestions=_question_suggestions("담보별 가입금액은 얼마야?"),
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
            limitations=_standard_limitations(facts),
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
        limitations=_standard_limitations(facts),
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
