import asyncio
from collections.abc import Generator
from queue import Queue
from threading import Event
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agents import Runner

from app.modules.qa.agent import runtime, service
from app.modules.qa.agent.contracts import QaAgentProgress
from app.modules.qa.agent.progress import QueuedAgentStreamItem, enqueue_stream_item
from app.modules.qa.context import QaContext


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
