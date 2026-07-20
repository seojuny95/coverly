"""Thin HTTP route for grounded insurance counseling."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.errors import ApiError
from app.integrations.openai.client import JsonCompleter, structured_completer
from app.modules.counsel.agent.definition import AgentStreamRunner, run_agent_streamed
from app.modules.counsel.answer import build_answer_stream
from app.modules.counsel.planner import CounselPlan, plan_counsel_turn
from app.modules.counsel.schemas import CounselRequest
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.service import InvalidPortfolioSessionToken

router = APIRouter(prefix="/counsel", tags=["counsel"])


def get_plan_completer() -> JsonCompleter:
    return structured_completer(CounselPlan)


def get_agent_stream_runner() -> AgentStreamRunner:
    return run_agent_streamed


PlanCompleterDep = Annotated[JsonCompleter, Depends(get_plan_completer)]
AgentStreamRunnerDep = Annotated[AgentStreamRunner, Depends(get_agent_stream_runner)]


@router.post("/stream")
async def stream_counsel_answer(
    request: CounselRequest,
    sessions: PortfolioSessionServiceDep,
    plan_completer: PlanCompleterDep,
    agent_stream_runner: AgentStreamRunnerDep,
) -> StreamingResponse:
    """Resolve the session, plan the turn, then stream the answer as SSE."""

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

    plan = await asyncio.to_thread(
        plan_counsel_turn,
        request.question,
        request.history,
        complete=plan_completer,
    )

    events = build_answer_stream(
        question=request.question,
        history=request.history,
        plan=plan,
        policies=list(snapshot.policies),
        policy_rag_session_ids=snapshot.rag_session_ids,
        model=get_settings().openai_model,
        agent_stream_runner=agent_stream_runner,
    )
    return StreamingResponse(events, media_type="text/event-stream")
