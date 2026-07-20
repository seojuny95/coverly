"""Thin HTTP route for grounded insurance counseling."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.errors import ApiError
from app.integrations.openai.client import JsonCompleter, structured_completer
from app.modules.counsel.agent.definition import AgentStreamRunner, run_agent_streamed
from app.modules.counsel.answer_stream import build_answer_stream
from app.modules.counsel.check_scope_and_rewrite import (
    ScopeAndRewriteResult,
    check_scope_and_rewrite,
)
from app.modules.counsel.schemas import CounselRequest
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.service import InvalidPortfolioSessionToken

router = APIRouter(prefix="/counsel", tags=["counsel"])


def get_check_completer() -> JsonCompleter:
    return structured_completer(ScopeAndRewriteResult)


def get_agent_stream_runner() -> AgentStreamRunner:
    return run_agent_streamed


CheckCompleterDep = Annotated[JsonCompleter, Depends(get_check_completer)]
AgentStreamRunnerDep = Annotated[AgentStreamRunner, Depends(get_agent_stream_runner)]


@router.post("/stream")
async def stream_counsel_answer(
    request: CounselRequest,
    sessions: PortfolioSessionServiceDep,
    check_completer: CheckCompleterDep,
    agent_stream_runner: AgentStreamRunnerDep,
) -> StreamingResponse:
    """Resolve the session and scope, then stream the agent's answer as SSE."""

    try:
        snapshot, check = await asyncio.gather(
            asyncio.to_thread(sessions.snapshot, request.session_id),
            asyncio.to_thread(
                check_scope_and_rewrite,
                request.question,
                request.history,
                complete=check_completer,
            ),
        )
    except InvalidPortfolioSessionToken:
        raise ApiError(
            status_code=403,
            code="INVALID_PORTFOLIO_SESSION",
            message="분석 세션이 만료됐어요. 보험증권을 다시 올려주세요.",
        ) from None

    events = build_answer_stream(
        check=check,
        policies=list(snapshot.policies),
        policy_rag_session_ids=snapshot.rag_session_ids,
        model=get_settings().openai_model,
        agent_stream_runner=agent_stream_runner,
    )
    return StreamingResponse(events, media_type="text/event-stream")
