import asyncio
import json
import threading
from collections.abc import AsyncIterator, Generator
from contextlib import suppress
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
from app.modules.qa.agent.contracts import (
    AgentCounselorDraft,
    QaAgentCompleted,
    QaAgentDelta,
    QaAgentDependencies,
    QaAgentMeta,
    QaAgentProgress,
)
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


class _FinishedStreamResult:
    """A run that emits one start-progress event, then finishes with a draft."""

    def __init__(self) -> None:
        self.hooks: Any = None

    async def stream_events(self) -> Any:
        await self.hooks.on_agent_start(None, None)
        if False:
            yield None

    def cancel(self, mode: str) -> None:  # pragma: no cover - not used here
        pass

    def final_output_as(self, *_args: object, **_kwargs: object) -> AgentCounselorDraft:
        return AgentCounselorDraft(answer_mode="tool_grounded", answer="가입 내용을 확인했어요.")


def test_stream_composes_meta_deltas_then_completed_from_injected_streamer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _FinishedStreamResult()

    def run_streamed(
        _runner: object,
        *_args: object,
        hooks: Any,
        **_kwargs: object,
    ) -> _FinishedStreamResult:
        result.hooks = hooks
        return result

    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(openai_api_key="test-key", openai_model="test-model"),
    )
    monkeypatch.setattr(runtime, "build_agent_input", lambda _context: "test input")
    monkeypatch.setattr(Runner, "run_streamed", classmethod(cast(Any, run_streamed)))

    validated = PortfolioQuestionResponse(
        status="answered", answer="가입 내용을 확인했어요.", citations=[], limitations=[]
    )

    def fake_validated(
        _context: QaContext,
        _draft: AgentCounselorDraft,
        dependencies: QaAgentDependencies,
    ) -> PortfolioQuestionResponse:
        # Register a deterministic tool result so the compose mode is grounded.
        dependencies.register("coverage_total", validated, trust_level="deterministic")
        return validated

    monkeypatch.setattr(runtime, "_validated_or_cached_response", fake_validated)

    def fake_streamer(_system: str, _user: str) -> Generator[str, None, None]:
        yield from ["가입 내용을 ", "확인했어요."]

    runner = runtime.OpenAiQaAgentRunner(compose_streamer=fake_streamer)
    context = cast(QaContext, SimpleNamespace(question="가입한 보험 확인해줘"))
    items = list(runner.stream(context))

    metas = [item for item in items if isinstance(item, QaAgentMeta)]
    deltas = [item for item in items if isinstance(item, QaAgentDelta)]
    completed = [item for item in items if isinstance(item, QaAgentCompleted)]

    assert len(metas) == 1
    assert metas[0].status == "answered"
    assert "".join(delta.text for delta in deltas) == "가입 내용을 확인했어요."
    assert len(completed) == 1
    assert completed[0].response is validated

    meta_index = items.index(metas[0])
    completed_index = items.index(completed[0])
    delta_indices = [index for index, item in enumerate(items) if isinstance(item, QaAgentDelta)]
    assert meta_index < min(delta_indices)
    assert max(delta_indices) < completed_index


def test_async_answer_stream_preserves_public_event_order() -> None:
    class _AsyncAgent:
        def run(self, _context: QaContext) -> PortfolioQuestionResponse:
            raise AssertionError("the async stream must be used")

        async def astream(
            self, _context: QaContext
        ) -> AsyncIterator[QaAgentProgress | QaAgentMeta | QaAgentDelta | QaAgentCompleted]:
            yield QaAgentProgress(stage="portfolio", text="증권을 확인하고 있어요.")
            yield QaAgentMeta(status="answered", generation="llm")
            yield QaAgentDelta(text="확인을 마쳤어요.")
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


def test_async_compose_phase_stays_cancellable_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The async path must offload the blocking compose iteration off the ASGI
    event loop. A compose streamer whose token read blocks must NOT freeze the
    loop: a cancellation raised mid-compose has to be honored promptly rather
    than being stalled until compose unblocks."""
    result = _FinishedStreamResult()

    def run_streamed(
        _runner: object,
        *_args: object,
        hooks: Any,
        **_kwargs: object,
    ) -> _FinishedStreamResult:
        result.hooks = hooks
        return result

    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(openai_api_key="test-key", openai_model="test-model"),
    )
    monkeypatch.setattr(runtime, "build_agent_input", lambda _context: "test input")
    monkeypatch.setattr(Runner, "run_streamed", classmethod(cast(Any, run_streamed)))

    validated = PortfolioQuestionResponse(
        status="answered", answer="가입 내용을 확인했어요.", citations=[], limitations=[]
    )

    def fake_validated(
        _context: QaContext,
        _draft: AgentCounselorDraft,
        dependencies: QaAgentDependencies,
    ) -> PortfolioQuestionResponse:
        # Deterministic tool result → composable mode → compose would run.
        dependencies.register("coverage_total", validated, trust_level="deterministic")
        return validated

    monkeypatch.setattr(runtime, "_validated_or_cached_response", fake_validated)

    compose_started = threading.Event()
    release = threading.Event()

    def blocking_streamer(_system: str, _user: str) -> Generator[str, None, None]:
        compose_started.set()
        # A per-token network read that blocks. Inline on the loop this would
        # freeze uvicorn; offloaded it must not.
        release.wait(timeout=5.0)
        yield "가입 내용을 확인했어요."

    runner = runtime.OpenAiQaAgentRunner(compose_streamer=blocking_streamer)
    context = cast(QaContext, SimpleNamespace(question="가입한 보험 확인해줘"))

    async def scenario() -> tuple[asyncio.Task[None], bool, list[Any]]:
        consumed: list[Any] = []

        async def consume() -> None:
            async for item in runner.astream(context):
                consumed.append(item)

        task: asyncio.Task[None] = asyncio.create_task(consume())
        loop = asyncio.get_running_loop()

        cancelled_promptly = threading.Event()
        forced = threading.Event()

        def watchdog() -> None:
            if not compose_started.wait(2.0):
                return
            loop.call_soon_threadsafe(task.cancel)
            # A responsive loop delivers the cancel well within this window.
            if not cancelled_promptly.wait(0.5):
                forced.set()
                release.set()  # rescue so a frozen loop cannot hang the test

        watcher = threading.Thread(target=watchdog, name="cancel-watchdog")
        watcher.start()

        with suppress(asyncio.CancelledError):
            await task
        cancelled_promptly.set()
        release.set()
        watcher.join(1.0)
        return task, forced.is_set(), consumed

    task, forced, consumed = asyncio.run(scenario())

    assert not forced, "compose blocked the event loop; cancellation was not honored in time"
    assert task.cancelled()
    assert any(isinstance(item, QaAgentMeta) for item in consumed)
