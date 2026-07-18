"""Thin HTTP route for grounded portfolio Q&A."""

import json
from collections.abc import Callable, Iterator
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.errors import api_error_responses
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.http import resolve_portfolio_snapshot
from app.modules.qa.agent.runtime import build_qa_agent_runner
from app.modules.qa.agent.service import stream_answer_with_agent
from app.modules.qa.schemas import PortfolioQuestionRequest
from app.modules.qa.streaming import QaStreamEvent

router = APIRouter(tags=["qa"])


class EventStreamOpenAPIResponse(JSONResponse):
    """Declare the event media type while runtime delivery remains streaming."""

    media_type = "text/event-stream"


PortfolioAnswerStreamer = Callable[..., Iterator[QaStreamEvent]]


def get_portfolio_answer_streamer() -> PortfolioAnswerStreamer:
    return partial(stream_answer_with_agent, agent_runner=build_qa_agent_runner())


PortfolioAnswerStreamerDep = Annotated[
    PortfolioAnswerStreamer,
    Depends(get_portfolio_answer_streamer),
]


@router.post(
    "/qa/stream",
    response_class=EventStreamOpenAPIResponse,
    responses={
        200: {
            "model": QaStreamEvent,
            "description": "Server-Sent Events: progress* → meta → delta* → end",
        },
        **api_error_responses(403, 503, response_media_type="application/json"),
    },
)
def ask_portfolio_question_stream(
    request: PortfolioQuestionRequest,
    stream_answer: PortfolioAnswerStreamerDep,
    sessions: PortfolioSessionServiceDep,
) -> StreamingResponse:
    """Stream the answer as Server-Sent Events: progress* → meta → delta* → end."""

    snapshot = resolve_portfolio_snapshot(sessions, request)

    def events() -> Iterator[str]:
        for event in stream_answer(
            request.question,
            list(snapshot.policies),
            demographics=request.demographics,
            history=request.history,
            policy_rag_session_ids=snapshot.rag_session_ids,
        ):
            yield f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
