"""Thin HTTP route for grounded insurance counseling."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.errors import ApiError, api_error_responses
from app.core.responses import EventStreamOpenAPIResponse
from app.integrations.openai.client import JsonCompleter, structured_completer
from app.modules.counsel.agent.definition import AgentStreamRunner, run_agent_streamed
from app.modules.counsel.answer import CounselStreamEvent, build_answer_stream
from app.modules.counsel.planner import CounselPlan, plan_counsel_turn
from app.modules.counsel.schemas import CounselRequest
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.service import (
    CounselTurnLimitReached,
    InvalidPortfolioSessionToken,
)

router = APIRouter(prefix="/counsel", tags=["counsel"])


def get_plan_completer() -> JsonCompleter:
    return structured_completer(CounselPlan)


def get_agent_stream_runner() -> AgentStreamRunner:
    return run_agent_streamed


PlanCompleterDep = Annotated[JsonCompleter, Depends(get_plan_completer)]
AgentStreamRunnerDep = Annotated[AgentStreamRunner, Depends(get_agent_stream_runner)]


@router.post(
    "/stream",
    response_class=EventStreamOpenAPIResponse,
    responses={
        200: {
            "model": CounselStreamEvent,
            "description": "Server-Sent Events: meta → delta* → end",
        },
        **api_error_responses(403, response_media_type="application/json"),
    },
)
async def stream_counsel_answer(
    request: CounselRequest,
    sessions: PortfolioSessionServiceDep,
    plan_completer: PlanCompleterDep,
    agent_stream_runner: AgentStreamRunnerDep,
) -> StreamingResponse:
    """Resolve the session, plan the turn, then stream the answer as SSE."""

    settings = get_settings()

    # The session token is an access boundary, so it is checked before the
    # question and history are sent anywhere.
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

    plan = await asyncio.to_thread(
        plan_counsel_turn,
        request.question,
        request.history,
        complete=plan_completer,
    )

    events = build_answer_stream(
        turns_remaining=turns_remaining,
        question=request.question,
        history=request.history,
        plan=plan,
        policies=list(snapshot.policies),
        policy_rag_session_ids=snapshot.rag_session_ids,
        model=settings.openai_model,
        agent_stream_runner=agent_stream_runner,
    )
    return StreamingResponse(events, media_type="text/event-stream")
