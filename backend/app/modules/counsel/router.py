"""Thin HTTP route for grounded insurance counseling."""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.errors import ApiError
from app.integrations.openai.client import JsonCompleter, structured_completer
from app.modules.counsel.agent.definition import AgentRunner, create_agent, run_agent
from app.modules.counsel.check_scope_and_rewrite import (
    ScopeAndRewriteResult,
    check_scope_and_rewrite,
)
from app.modules.counsel.context import CounselContext
from app.modules.counsel.schemas import CounselRequest
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.service import InvalidPortfolioSessionToken

router = APIRouter(prefix="/counsel", tags=["counsel"])

_OUT_OF_SCOPE_ANSWER = (
    "이 질문은 보험 상담 범위 밖이라 답하기 어려워요. 가입 보험, 담보, 약관, "
    "청구처럼 보험과 관련된 내용으로 물어봐 주세요."
)


def get_check_completer() -> JsonCompleter:
    return structured_completer(ScopeAndRewriteResult)


def get_agent_runner() -> AgentRunner:
    return run_agent


CheckCompleterDep = Annotated[JsonCompleter, Depends(get_check_completer)]
AgentRunnerDep = Annotated[AgentRunner, Depends(get_agent_runner)]


@router.post("/stream")
async def stream_counsel_answer(
    request: CounselRequest,
    sessions: PortfolioSessionServiceDep,
    check_completer: CheckCompleterDep,
    agent_runner: AgentRunnerDep,
) -> dict[str, object]:
    """Resolve the session, rewrite/scope-gate the question, then run the agent."""

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

    if not check.in_scope:
        return {
            "answer": _OUT_OF_SCOPE_ANSWER,
            "in_scope": False,
            "rewritten_question": check.rewritten_question,
        }

    context = CounselContext(
        policies=list(snapshot.policies),
        policy_rag_session_ids=snapshot.rag_session_ids,
    )

    settings = get_settings()
    agent = create_agent(settings.openai_model)
    result = await agent_runner(agent, check.rewritten_question, context)

    return {
        "answer": str(result.final_output),
        "in_scope": True,
        "rewritten_question": check.rewritten_question,
    }
