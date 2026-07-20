"""Stream one resolved counsel answer as SSE events."""

from collections.abc import AsyncIterator

from app.modules.counsel.agent.definition import AgentStreamRunner, create_agent
from app.modules.counsel.answer.brief import build_agent_input
from app.modules.counsel.answer.escalation import route_answer
from app.modules.counsel.answer.events import (
    CounselDeltaEvent,
    CounselEndEvent,
    CounselMetaEvent,
    serialize_event,
)
from app.modules.counsel.composer import compose_fact_answer
from app.modules.counsel.context import CounselContext
from app.modules.counsel.fact_executor import execute_fact_tasks
from app.modules.counsel.planner import CounselPlan
from app.modules.portfolio.schemas import PolicyInput

_OUT_OF_SCOPE_ANSWER = (
    "이 질문은 보험 상담 범위 밖이라 답하기 어려워요. 가입 보험, 담보, 약관, "
    "청구처럼 보험과 관련된 내용으로 물어봐 주세요."
)


async def build_answer_stream(
    *,
    question: str,
    plan: CounselPlan,
    policies: list[PolicyInput],
    policy_rag_session_ids: tuple[str, ...],
    model: str,
    agent_stream_runner: AgentStreamRunner,
) -> AsyncIterator[str]:
    """Yield serialized SSE events: one meta event, then deltas, then end."""

    yield serialize_event(
        CounselMetaEvent(
            in_scope=plan.in_scope,
            rewritten_question=plan.rewritten_question,
            excluded_note=plan.excluded_note,
        )
    )

    if not plan.in_scope:
        yield serialize_event(CounselDeltaEvent(text=_OUT_OF_SCOPE_ANSWER))
        yield serialize_event(CounselEndEvent())
        return

    execution = execute_fact_tasks(plan, policies)
    composed = compose_fact_answer(execution)
    route = route_answer(
        plan,
        execution,
        composed,
        asked_texts=(question, plan.rewritten_question),
    )

    if route.fact_answer is not None:
        separator = "\n\n" if route.run_agent else ""
        yield serialize_event(CounselDeltaEvent(text=f"{route.fact_answer}{separator}"))

    if not route.run_agent:
        yield serialize_event(CounselEndEvent())
        return

    context = CounselContext(policies=policies, policy_rag_session_ids=policy_rag_session_ids)
    agent_input = build_agent_input(
        plan.rewritten_question,
        facts=composed,
        facts_shown=route.shows_facts,
        needs_hedge=route.needs_hedge,
    )

    async for chunk in agent_stream_runner(create_agent(model), agent_input, context):
        yield serialize_event(CounselDeltaEvent(text=chunk))

    yield serialize_event(CounselEndEvent())
