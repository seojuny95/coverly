"""Thin HTTP route for grounded portfolio Q&A."""

import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.qa import PortfolioQuestionRequest, PortfolioQuestionResponse
from app.services.qa.service import answer_portfolio_question, stream_portfolio_answer

router = APIRouter(tags=["qa"])


@router.post("/qa", response_model=PortfolioQuestionResponse)
def ask_portfolio_question(request: PortfolioQuestionRequest) -> PortfolioQuestionResponse:
    return answer_portfolio_question(
        request.question,
        request.policies,
        demographics=request.demographics,
        history=request.history,
    )


@router.post("/qa/stream")
def ask_portfolio_question_stream(request: PortfolioQuestionRequest) -> StreamingResponse:
    """Stream the answer as Server-Sent Events: meta → delta* → end."""

    def events() -> Iterator[str]:
        for event in stream_portfolio_answer(
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
