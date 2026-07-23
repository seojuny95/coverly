"""Thin HTTP route for the single-agent qa answer.

A request is resolved to a portfolio snapshot, then handed to one agent call
whose text is forwarded to the client as-is -- no slot rendering, no planner
step, no backstop. See agent.py's module docstring for why nothing rewrites it.

meta.in_scope/answered_question/excluded_note exist only to satisfy the SSE
event schema (events.py); this design has no separate scope-classification
step, so they carry placeholder values (scope is expressed in the answer's
prose, not a precomputed flag). The frontend doesn't read these three today;
only turns_remaining is live. An eval judging "did this turn correctly
decline" must read the answer text, not this field.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.errors import ApiError, api_error_responses
from app.core.responses import EventStreamOpenAPIResponse
from app.integrations.openai import ConversationMessage
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.service import (
    CounselTurnLimitReached,
    InvalidPortfolioSessionToken,
    PortfolioSessionService,
)
from app.modules.qa.agent import AgentStreamRunner, create_agent, run_agent_streamed
from app.modules.qa.context import QaContext
from app.modules.qa.events import (
    QaDeltaEvent,
    QaEndEvent,
    QaMetaEvent,
    QaStreamEvent,
    serialize_event,
)
from app.modules.qa.history import recent_turns
from app.modules.qa.pii import mask_qa_pii, masked_history
from app.modules.qa.schemas import QaMessage, QaRequest

router = APIRouter(prefix="/qa", tags=["qa"])
logger = logging.getLogger(__name__)
_QA_STREAM_FAILURE_MESSAGE = (
    "답을 가져오지 못했어요. 대화 내용은 그대로 있으니 잠시 후 다시 질문해주세요."
)


def get_agent_stream_runner() -> AgentStreamRunner:
    return run_agent_streamed


AgentStreamRunnerDep = Annotated[AgentStreamRunner, Depends(get_agent_stream_runner)]


@router.post(
    "/stream",
    response_class=EventStreamOpenAPIResponse,
    responses={
        200: {
            "model": QaStreamEvent,
            "description": "Server-Sent Events: meta → delta* → end",
        },
        **api_error_responses(403, 429, response_media_type="application/json"),
    },
)
async def stream_qa_answer(
    request: QaRequest,
    sessions: PortfolioSessionServiceDep,
    agent_stream_runner: AgentStreamRunnerDep,
) -> StreamingResponse:
    """Resolve the session, then stream one agent's answer as SSE."""

    settings = get_settings()

    try:
        snapshot = await asyncio.to_thread(sessions.snapshot, request.session_id)
    except InvalidPortfolioSessionToken:
        raise ApiError(
            status_code=403,
            code="INVALID_PORTFOLIO_SESSION",
            message="분석 세션이 만료됐어요. 보험증권을 다시 올려주세요.",
        ) from None

    try:
        turns_remaining = await asyncio.to_thread(
            sessions.consume_counsel_turn,
            request.session_id,
            max_turns=settings.counsel_max_turns_per_session,
        )
    except CounselTurnLimitReached:
        raise ApiError(
            status_code=429,
            code="COUNSEL_TURN_LIMIT_REACHED",
            message=(
                f"이 분석에서는 질문을 {settings.counsel_max_turns_per_session}번까지 할 수 "
                "있어요. 새 증권을 올려 분석을 다시 시작하면 질문을 이어갈 수 있어요."
            ),
        ) from None

    question = mask_qa_pii(request.question)
    history = masked_history(
        recent_turns(request.history, max_turns=settings.counsel_history_turns)
    )

    events = _build_event_stream(
        session_id=request.session_id,
        sessions=sessions,
        turns_remaining=turns_remaining,
        question=question,
        history=history,
        policies=list(snapshot.policies),
        policy_rag_session_ids=snapshot.rag_session_ids,
        model=settings.openai_model,
        agent_stream_runner=agent_stream_runner,
    )
    return StreamingResponse(events, media_type="text/event-stream")


async def _build_event_stream(
    *,
    session_id: str,
    sessions: PortfolioSessionService,
    turns_remaining: int,
    question: str,
    history: list[QaMessage],
    policies: list[PolicyInput],
    policy_rag_session_ids: tuple[str, ...],
    model: str,
    agent_stream_runner: AgentStreamRunner,
) -> AsyncIterator[str]:
    yield serialize_event(
        QaMetaEvent(
            in_scope=True,
            answered_question=question,
            excluded_note=None,
            turns_remaining=turns_remaining,
        )
    )

    context = QaContext(policies=policies, policy_rag_session_ids=policy_rag_session_ids)
    agent = create_agent(model)
    conversation: list[ConversationMessage] = [
        ConversationMessage(role=message.role, content=message.content) for message in history
    ]
    conversation.append(ConversationMessage(role="user", content=question))

    try:
        async for delta in agent_stream_runner(agent, conversation, context):
            if delta:
                yield serialize_event(QaDeltaEvent(text=delta))
    except asyncio.CancelledError:
        await _refund_counsel_turn_best_effort(sessions, session_id)
        raise
    except Exception as exc:
        logger.warning("qa_stream_failed", extra={"error_type": type(exc).__name__})
        await _refund_counsel_turn_best_effort(sessions, session_id)
        yield serialize_event(QaDeltaEvent(text=_QA_STREAM_FAILURE_MESSAGE))

    yield serialize_event(QaEndEvent())


async def _refund_counsel_turn_best_effort(
    sessions: PortfolioSessionService,
    session_id: str,
) -> None:
    try:
        await asyncio.to_thread(sessions.refund_counsel_turn, session_id)
    except Exception as exc:
        logger.warning(
            "qa_turn_refund_failed",
            extra={"error_type": type(exc).__name__},
        )
