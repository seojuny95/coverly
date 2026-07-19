import asyncio
import json
from collections.abc import AsyncIterator, Generator
from queue import Queue
from threading import Event
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agents import Runner
from fastapi import FastAPI
from starlette.types import Message, Scope

from app.modules.portfolio.session.dependencies import get_portfolio_session_service
from app.modules.portfolio.session.models import PortfolioSessionSnapshot
from app.modules.qa.agent import runtime, service
from app.modules.qa.agent.contracts import QaAgentCompleted, QaAgentProgress
from app.modules.qa.agent.progress import QueuedAgentStreamItem, enqueue_stream_item
from app.modules.qa.context import QaContext
from app.modules.qa.router import router as qa_router
from app.modules.qa.schemas import PortfolioQuestionResponse


class _BlockingStreamResult:
    def __init__(self) -> None:
        self.hooks: Any = None
        self.cancel_mode: str | None = None
        self.cancelled = Event()
        self.finished = Event()

    async def stream_events(self) -> Any:
        try:
            await self.hooks.on_agent_start(None, None)
            while not self.cancelled.is_set():
                await asyncio.sleep(0.01)
        finally:
            self.finished.set()
        if False:
            yield None

    def cancel(self, mode: str) -> None:
        self.cancel_mode = mode
        self.cancelled.set()

    def final_output_as(self, *_args: object, **_kwargs: object) -> object:
        raise AssertionError("a cancelled run must not build a final response")


def test_closing_agent_stream_cancels_and_joins_sdk_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _BlockingStreamResult()

    def run_streamed(
        _runner: object,
        *_args: object,
        hooks: Any,
        **_kwargs: object,
    ) -> _BlockingStreamResult:
        result.hooks = hooks
        return result

    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="test-key",
            openai_model="test-model",
        ),
    )
    monkeypatch.setattr(runtime, "build_agent_input", lambda _context: "test input")
    monkeypatch.setattr(
        Runner,
        "run_streamed",
        classmethod(cast(Any, run_streamed)),
    )

    stream = cast(
        Generator[Any, None, None],
        runtime.OpenAiQaAgentRunner().stream(cast(QaContext, object())),
    )

    first_item = next(stream)
    assert isinstance(first_item, QaAgentProgress)

    stream.close()

    assert result.cancel_mode == "immediate"
    assert result.finished.wait(timeout=0.1)


def test_bounded_stream_queue_stops_waiting_after_cancellation() -> None:
    queue: Queue[QueuedAgentStreamItem] = Queue(maxsize=1)
    cancellation_requested = Event()
    queue.put(QaAgentProgress(stage="routing", text="확인 중"))
    cancellation_requested.set()

    enqueued = enqueue_stream_item(
        queue,
        cancellation_requested,
        QaAgentProgress(stage="grounding", text="근거 확인 중"),
    )

    assert enqueued is False
    assert queue.qsize() == 1


def test_closing_answer_stream_closes_agent_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_stream_closed = Event()

    class _CloseAwareAgent:
        def stream(self, _context: QaContext) -> Generator[QaAgentProgress, None, None]:
            try:
                yield QaAgentProgress(stage="routing", text="확인 중")
            finally:
                agent_stream_closed.set()

    monkeypatch.setattr(
        service,
        "build_qa_context",
        lambda *_args, **_kwargs: cast(QaContext, object()),
    )
    answer_stream = cast(
        Generator[Any, None, None],
        service.stream_answer_with_agent(
            "가입한 보험을 확인해줘",
            [],
            agent_runner=cast(Any, _CloseAwareAgent()),
        ),
    )

    assert next(answer_stream).type == "progress"

    answer_stream.close()

    assert agent_stream_closed.is_set()


def test_asgi_disconnect_cancels_async_agent_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _BlockingStreamResult()

    def run_streamed(
        _runner: object,
        *_args: object,
        hooks: Any,
        **_kwargs: object,
    ) -> _BlockingStreamResult:
        result.hooks = hooks
        return result

    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="test-key",
            openai_model="test-model",
        ),
    )
    monkeypatch.setattr(runtime, "build_agent_input", lambda _context: "test input")
    monkeypatch.setattr(
        Runner,
        "run_streamed",
        classmethod(cast(Any, run_streamed)),
    )

    class _Sessions:
        def snapshot(
            self,
            token: str,
            *,
            policy_ids: list[str] | None = None,
        ) -> PortfolioSessionSnapshot:
            return PortfolioSessionSnapshot(
                session_id="portfolio-1",
                version=1,
                policies=(),
                rag_session_ids=(),
            )

    app = FastAPI()
    app.include_router(qa_router)
    app.dependency_overrides[get_portfolio_session_service] = lambda: _Sessions()

    async def run_disconnected_request() -> None:
        request_messages: asyncio.Queue[Message] = asyncio.Queue()
        payload = json.dumps(
            {
                "question": "가입한 보험을 확인해줘",
                "portfolioSessionToken": "portfolio-token",
                "policyIds": ["00000000-0000-0000-0000-000000000001"],
            }
        ).encode()
        request_messages.put_nowait({"type": "http.request", "body": payload, "more_body": False})
        disconnect_sent = False
        sent_messages: list[Message] = []

        async def receive() -> Message:
            return await request_messages.get()

        async def send(message: Message) -> None:
            nonlocal disconnect_sent
            sent_messages.append(message)
            body = message.get("body", b"")
            if (
                message["type"] == "http.response.body"
                and isinstance(body, bytes)
                and b'"type": "progress"' in body
                and not disconnect_sent
            ):
                disconnect_sent = True
                request_messages.put_nowait({"type": "http.disconnect"})

        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/qa/stream",
            "raw_path": b"/qa/stream",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        await asyncio.wait_for(
            app(
                scope,
                receive,
                send,
            ),
            timeout=1.0,
        )
        assert disconnect_sent, sent_messages

    asyncio.run(run_disconnected_request())

    assert result.cancel_mode == "immediate"
    assert result.finished.wait(timeout=0.1)


def test_async_answer_stream_preserves_public_event_order() -> None:
    class _AsyncAgent:
        def run(self, _context: QaContext) -> PortfolioQuestionResponse:
            raise AssertionError("the async stream must be used")

        async def astream(
            self, _context: QaContext
        ) -> AsyncIterator[QaAgentProgress | QaAgentCompleted]:
            yield QaAgentProgress(stage="portfolio", text="증권을 확인하고 있어요.")
            yield QaAgentCompleted(
                PortfolioQuestionResponse(
                    status="answered",
                    answer="확인을 마쳤어요.",
                    citations=[],
                    limitations=[],
                )
            )

    async def collect_events() -> list[Any]:
        return [
            event
            async for event in service.stream_answer_with_agent_async(
                "가입한 보험을 보여줘",
                [],
                agent_runner=cast(Any, _AsyncAgent()),
            )
        ]

    events = asyncio.run(collect_events())

    assert [event.type for event in events] == ["progress", "meta", "delta", "end"]
