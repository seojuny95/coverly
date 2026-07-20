"""Thin HTTP route for grounded portfolio Q&A."""

import asyncio
import json
from collections.abc import AsyncIterable, AsyncIterator, Callable, Iterator
from contextlib import suppress
from functools import partial
from typing import Annotated

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.core.errors import api_error_responses
from app.core.responses import EventStreamOpenAPIResponse
from app.modules.portfolio.session.dependencies import PortfolioSessionServiceDep
from app.modules.portfolio.session.http import resolve_portfolio_snapshot
from app.modules.qa.agent.runtime import build_qa_agent_runner
from app.modules.qa.agent.service import stream_answer_with_agent_async
from app.modules.qa.schemas import PortfolioQuestionRequest
from app.modules.qa.streaming import QaStreamEvent

router = APIRouter(tags=["qa"])


class DisconnectAwareStreamingResponse(StreamingResponse):
    """Close the response iterator as soon as ASGI reports a disconnect."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            async with anyio.create_task_group() as task_group:

                async def stream_response() -> None:
                    try:
                        await self.stream_response(send)
                    except OSError:
                        pass
                    finally:
                        task_group.cancel_scope.cancel()

                async def watch_disconnect() -> None:
                    try:
                        await self.listen_for_disconnect(receive)
                    finally:
                        task_group.cancel_scope.cancel()

                task_group.start_soon(stream_response)
                task_group.start_soon(watch_disconnect)
        finally:
            close = getattr(self.body_iterator, "aclose", None)
            if callable(close):
                with suppress(asyncio.CancelledError):
                    await close()

        if self.background is not None:
            await self.background()


type PortfolioAnswerStream = Iterator[QaStreamEvent] | AsyncIterator[QaStreamEvent]
PortfolioAnswerStreamer = Callable[..., PortfolioAnswerStream]


def get_portfolio_answer_streamer() -> PortfolioAnswerStreamer:
    return partial(stream_answer_with_agent_async, agent_runner=build_qa_agent_runner())


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
async def ask_portfolio_question_stream(
    request: PortfolioQuestionRequest,
    stream_answer: PortfolioAnswerStreamerDep,
    sessions: PortfolioSessionServiceDep,
) -> StreamingResponse:
    """Stream the answer as Server-Sent Events: progress* → meta → delta* → end."""

    snapshot = await asyncio.to_thread(resolve_portfolio_snapshot, sessions, request)

    async def events() -> AsyncIterator[str]:
        answer_events = stream_answer(
            request.question,
            list(snapshot.policies),
            demographics=request.demographics,
            history=request.history,
            policy_rag_session_ids=snapshot.rag_session_ids,
        )
        try:
            if isinstance(answer_events, AsyncIterable):
                async for event in answer_events:
                    yield _serialize_event(event)
            else:
                iterator = iter(answer_events)
                while True:
                    next_event: QaStreamEvent | None = await asyncio.to_thread(
                        _next_sync_event, iterator
                    )
                    if next_event is None:
                        break
                    yield _serialize_event(next_event)
        finally:
            if isinstance(answer_events, AsyncIterable):
                close = getattr(answer_events, "aclose", None)
                if callable(close):
                    await close()
            else:
                close = getattr(answer_events, "close", None)
                if callable(close):
                    with suppress(ValueError):
                        await asyncio.to_thread(close)

    return DisconnectAwareStreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _next_sync_event(iterator: Iterator[QaStreamEvent]) -> QaStreamEvent | None:
    try:
        return next(iterator)
    except StopIteration:
        return None


def _serialize_event(event: QaStreamEvent) -> str:
    return f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
