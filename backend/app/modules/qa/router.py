"""Thin HTTP route for grounded portfolio Q&A."""

import json
from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.modules.qa.generation import QaStreamEvent
from app.modules.qa.schemas import PortfolioQuestionRequest
from app.modules.qa.service import stream_portfolio_answer

router = APIRouter(tags=["qa"])

PortfolioAnswerStreamer = Callable[..., Iterator[QaStreamEvent]]


def get_portfolio_answer_streamer() -> PortfolioAnswerStreamer:
    return stream_portfolio_answer


PortfolioAnswerStreamerDep = Annotated[
    PortfolioAnswerStreamer,
    Depends(get_portfolio_answer_streamer),
]


@router.post("/qa/stream")
def ask_portfolio_question_stream(
    request: PortfolioQuestionRequest,
    stream_answer: PortfolioAnswerStreamerDep,
) -> StreamingResponse:
    """Stream the answer as Server-Sent Events: meta → delta* → end."""

    def events() -> Iterator[str]:
        for event in stream_answer(
            request.question,
            request.policies,
            demographics=request.demographics,
            history=request.history,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
