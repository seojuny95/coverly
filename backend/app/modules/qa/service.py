"""Public orchestration for grounded portfolio Q&A."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass

from app.integrations.openai.client import JsonCompleter, TextStreamer
from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent import (
    QaAgentRunner,
    QaAgentUnavailable,
    requires_official_web,
)
from app.modules.qa.context import (
    QaContext,
    build_qa_context,
    claim_targets,
    context_with_question,
)
from app.modules.qa.contracts import InsuredDemographics
from app.modules.qa.generation import (
    QaStreamEvent,
    answer_text_chunks,
    generate_consultation_answer,
    stream_consultation_answer,
)
from app.modules.qa.plan_resolution import (
    answer_question_plan,
    answer_scope_only_plan,
    clarification_response,
    is_scope_only_plan,
)
from app.modules.qa.planning import QuestionPlan, plan_questions
from app.modules.qa.resolvers import (
    OfficialAnswerer,
    context_fallback,
    contextual_suggestions,
    demographic_notice,
    resolve_fast_answer,
    resolve_precomputed_answer,
    standard_limitations,
    with_demographics,
)
from app.modules.qa.schemas import ConversationMessage, PortfolioQuestionResponse
from app.rag.official.answer import answer_official_question
from app.rag.policy import (
    PolicyGenerationResult as _PolicyGenerationResult,
)
from app.rag.policy import (
    generate_policy_answer,
    retrieve_policy_context,
)

PolicyGenerationResult = _PolicyGenerationResult
logger = logging.getLogger(__name__)

# Keep the established service-module bindings available for callers and tests
# while the implementations live in responsibility-focused modules.
_QaContext = QaContext
_build_qa_context = build_qa_context
_context_with_question = context_with_question
_clarification_response = clarification_response
_is_scope_only_plan = is_scope_only_plan
_answer_scope_only_plan = answer_scope_only_plan
_context_fallback = context_fallback
_contextual_suggestions = contextual_suggestions
_standard_limitations = standard_limitations
_demographic_notice = demographic_notice
_with_demographics = with_demographics


@dataclass(frozen=True)
class _QuestionTurn:
    question: str
    history: list[ConversationMessage]
    plan: QuestionPlan | None


def answer_portfolio_question(
    question: str,
    policies: list[PolicyInput],
    *,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
    complete: JsonCompleter | None = None,
    official_answer: OfficialAnswerer | None = None,
    plan: JsonCompleter | None = None,
    agent_runner: QaAgentRunner | None = None,
) -> PortfolioQuestionResponse:
    """Answer with cited facts, or refuse conclusions that require policy terms."""

    turn = _plan_question_turn(
        question,
        history,
        plan,
        allow_default_completion=not (agent_runner is not None and plan is None),
    )
    if turn.plan is not None:
        if turn.plan.clarification is not None:
            return _clarification_response(turn.plan.clarification)
        if _is_scope_only_plan(turn.plan):
            return _answer_scope_only_plan(turn.plan)
        context = _build_qa_context(turn.question, policies, demographics, turn.history)
        if len(turn.plan.questions) != 1 or turn.plan.questions[0].scope != "insurance":
            return _answer_question_plan(context, turn.plan, complete, official_answer)
        context = _context_with_question(context, turn.plan.questions[0].resolved)
        agent_response = _answer_with_agent(context, agent_runner)
        if agent_response is not None:
            return agent_response
        if agent_runner is not None:
            return _agent_fallback(context)
        precomputed = _precomputed_answer(
            context,
            complete,
            official_answer,
            pass_complete=True,
        )
        if precomputed is not None:
            return precomputed
        return _answer_consultation(context, complete)

    context = _build_qa_context(turn.question, policies, demographics, turn.history)
    agent_response = _answer_with_agent(context, agent_runner)
    if agent_response is not None:
        return agent_response
    if agent_runner is not None:
        return _agent_fallback(context)
    precomputed = _precomputed_answer(
        context,
        complete,
        official_answer,
        pass_complete=True,
    )
    if precomputed is not None:
        return precomputed
    return _answer_consultation(context, complete)


def stream_portfolio_answer(
    question: str,
    policies: list[PolicyInput],
    *,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
    stream: TextStreamer | None = None,
    official_answer: OfficialAnswerer | None = None,
    plan: JsonCompleter | None = None,
    agent_runner: QaAgentRunner | None = None,
) -> Iterator[QaStreamEvent]:
    """Stream deterministic routes at once and the consultation route incrementally."""

    turn = _plan_question_turn(
        question,
        history,
        plan,
        allow_default_completion=not (agent_runner is not None and plan is None),
    )
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

    if stream is None and agent_runner is not None:
        agent_response = _answer_with_agent(context, agent_runner)
        if agent_response is not None:
            yield from _stream_response(agent_response)
            return
        yield from _stream_response(_agent_fallback(context))
        return

    if not requires_official_web(context.question):
        fast_response = resolve_fast_answer(context)
        if fast_response is not None:
            yield from _stream_response(fast_response)
            return

    precomputed = _precomputed_answer(
        context,
        None,
        official_answer,
        pass_complete=False,
    )
    if precomputed is not None:
        yield from _stream_response(precomputed)
        return

    yield from _stream_context(context, stream, official_answer)


def _answer_context(
    context: QaContext,
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

    return _answer_consultation(context, complete)


def _answer_consultation(
    context: QaContext,
    complete: JsonCompleter | None,
) -> PortfolioQuestionResponse:

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


def _answer_with_agent(
    context: QaContext,
    agent_runner: QaAgentRunner | None,
) -> PortfolioQuestionResponse | None:
    if agent_runner is None:
        return None
    runner = agent_runner
    try:
        return runner.run(context)
    except QaAgentUnavailable:
        return None
    except Exception as exc:
        logger.warning(
            "QA agent failed with %s; using grounded fallback",
            type(exc).__name__,
        )
        return None


def _agent_fallback(context: QaContext) -> PortfolioQuestionResponse:
    return _with_demographics(_context_fallback(context), context.insured)


def _precomputed_answer(
    context: QaContext,
    complete: JsonCompleter | None,
    official_answer: OfficialAnswerer | None,
    *,
    pass_complete: bool,
) -> PortfolioQuestionResponse | None:
    if requires_official_web(context.question):
        return None
    return _resolve_precomputed_answer(
        context,
        try_official=complete is None or official_answer is not None,
        official_answer=official_answer,
        complete=complete,
        pass_complete=pass_complete,
    )


def _stream_context(
    context: QaContext,
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
        claim_targets=claim_targets(context),
        stream=stream,
    )


def _answer_question_plan(
    context: QaContext,
    question_plan: QuestionPlan,
    complete: JsonCompleter | None,
    official_answer: OfficialAnswerer | None,
) -> PortfolioQuestionResponse:
    return answer_question_plan(
        context,
        question_plan,
        complete,
        official_answer,
        _answer_context,
    )


def _resolve_precomputed_answer(
    context: QaContext,
    *,
    try_official: bool,
    official_answer: OfficialAnswerer | None,
    complete: JsonCompleter | None,
    pass_complete: bool,
) -> PortfolioQuestionResponse | None:
    return resolve_precomputed_answer(
        context,
        try_official=try_official,
        official_answer=official_answer,
        default_official_answer=answer_official_question,
        complete=complete,
        pass_complete=pass_complete,
        retrieve_policy=retrieve_policy_context,
        generate_policy=generate_policy_answer,
    )


def _plan_question_turn(
    question: str,
    history: list[ConversationMessage] | None,
    complete: JsonCompleter | None,
    *,
    allow_default_completion: bool = True,
) -> _QuestionTurn:
    normalized_question = question.strip()
    conversation_history = history or []
    return _QuestionTurn(
        question=normalized_question,
        history=conversation_history,
        plan=plan_questions(
            normalized_question,
            conversation_history,
            complete=complete,
            allow_default_completion=allow_default_completion,
        ),
    )


def _stream_response(response: PortfolioQuestionResponse) -> Iterator[QaStreamEvent]:
    """Emit a fully computed answer as display-sized SSE deltas."""

    yield {"type": "meta", "status": response.status, "generation": response.generation}
    for chunk in answer_text_chunks(response.answer):
        yield {"type": "delta", "text": chunk}
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


def _stream_clarification(question: str) -> Iterator[QaStreamEvent]:
    yield {"type": "meta", "status": "clarify", "generation": "fallback"}
    for chunk in answer_text_chunks(question):
        yield {"type": "delta", "text": chunk}
    yield {
        "type": "end",
        "status": "clarify",
        "generation": "fallback",
        "citations": [],
        "limitations": [],
        "suggestions": [],
        "claim_channels": None,
    }
