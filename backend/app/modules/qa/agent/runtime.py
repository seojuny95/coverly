"""Runtime and sync-to-stream bridge for the QA agent."""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from queue import Empty, Queue
from threading import Event, Thread

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    Runner,
    RunResultStreaming,
)
from agents.models.openai_provider import OpenAIProvider

from app.core.config import get_settings
from app.integrations.openai.client import JsonCompleter, TextStreamer, stream_completion
from app.modules.qa.agent.answer_stream import safe_answer_stream_items
from app.modules.qa.agent.contracts import (
    AgentCounselorDraft,
    OfficialAnswerer,
    QaAgentDependencies,
    QaAgentRunner,
    QaAgentStreamItem,
    QaAgentUnavailable,
    RegisteredToolResult,
)
from app.modules.qa.agent.definition import create_qa_agent
from app.modules.qa.agent.progress import (
    AsyncProgressHooks,
    ProgressHooks,
    QueuedAgentStreamItem,
    enqueue_stream_item,
)
from app.modules.qa.agent.prompt import build_agent_input
from app.modules.qa.agent.selection import select_tool_result
from app.modules.qa.agent.validation import validated_agent_response
from app.modules.qa.context import QaContext
from app.modules.qa.response_support import out_of_scope_response
from app.modules.qa.schemas import PortfolioQuestionResponse
from app.modules.qa.tools.web_search import OfficialWebSearcher, default_official_web_search

logger = logging.getLogger(__name__)

_STREAM_QUEUE_CAPACITY = 16
_CANCELLATION_POLL_SECONDS = 0.05
_WORKER_JOIN_TIMEOUT_SECONDS = 2.0


def build_qa_agent_runner(
    *,
    complete: JsonCompleter | None = None,
    classify_input: JsonCompleter | None = None,
    classify_output: JsonCompleter | None = None,
    official_answer: OfficialAnswerer | None = None,
    web_search: OfficialWebSearcher = default_official_web_search,
    model: str | None = None,
    compose_streamer: TextStreamer = stream_completion,
) -> QaAgentRunner:
    return OpenAiQaAgentRunner(
        complete=complete,
        classify_input=classify_input,
        classify_output=classify_output,
        official_answer=official_answer,
        web_search=web_search,
        model=model,
        compose_streamer=compose_streamer,
    )


class OpenAiQaAgentRunner:
    """Run one OpenAI agent with local grounded tools and SDK guardrails."""

    def __init__(
        self,
        *,
        complete: JsonCompleter | None = None,
        classify_input: JsonCompleter | None = None,
        classify_output: JsonCompleter | None = None,
        official_answer: OfficialAnswerer | None = None,
        web_search: OfficialWebSearcher = default_official_web_search,
        model: str | None = None,
        compose_streamer: TextStreamer = stream_completion,
    ) -> None:
        self._complete = complete
        self._classify_input = classify_input
        self._classify_output = classify_output
        self._official_answer = official_answer
        self._web_search = web_search
        self._model = model
        self._compose_streamer = compose_streamer

    def run(self, context: QaContext) -> PortfolioQuestionResponse:
        settings = get_settings()
        if not settings.openai_api_key:
            raise QaAgentUnavailable("OPENAI_API_KEY is not configured")

        dependencies = self._dependencies(context)
        try:
            result = Runner.run_sync(
                create_qa_agent(self._model or settings.openai_model),
                input=build_agent_input(context),
                context=dependencies,
                max_turns=6,
                run_config=_run_config(settings.openai_api_key),
            )
        except InputGuardrailTripwireTriggered:
            return out_of_scope_response(context)
        except OutputGuardrailTripwireTriggered:
            fallback = _unambiguous_tool_fallback(dependencies)
            if fallback is not None:
                return fallback
            raise
        draft = result.final_output_as(AgentCounselorDraft, raise_if_incorrect_type=True)
        return _validated_or_cached_response(context, draft, dependencies)

    def stream(self, context: QaContext) -> Iterator[QaAgentStreamItem]:
        settings = get_settings()
        if not settings.openai_api_key:
            raise QaAgentUnavailable("OPENAI_API_KEY is not configured")

        dependencies = self._dependencies(context)
        queue: Queue[QueuedAgentStreamItem] = Queue(maxsize=_STREAM_QUEUE_CAPACITY)
        cancellation_requested = Event()
        worker = Thread(
            target=_run_streamed_worker,
            args=(
                context,
                dependencies,
                self._model or settings.openai_model,
                settings.openai_api_key,
                queue,
                cancellation_requested,
                self._compose_streamer,
            ),
            daemon=True,
            name="coverly-qa-agent",
        )
        worker.start()
        try:
            while True:
                try:
                    item = queue.get(timeout=_CANCELLATION_POLL_SECONDS)
                except Empty:
                    if cancellation_requested.is_set():
                        break
                    continue
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            cancellation_requested.set()
            worker.join(timeout=_WORKER_JOIN_TIMEOUT_SECONDS)
            if worker.is_alive():
                logger.warning("QA agent worker did not stop within the cancellation timeout")

    async def astream(self, context: QaContext) -> AsyncIterator[QaAgentStreamItem]:
        """Stream on the ASGI event loop so request cancellation reaches the SDK."""

        settings = get_settings()
        if not settings.openai_api_key:
            raise QaAgentUnavailable("OPENAI_API_KEY is not configured")

        queue: asyncio.Queue[QueuedAgentStreamItem] = asyncio.Queue(maxsize=_STREAM_QUEUE_CAPACITY)
        worker = asyncio.create_task(
            _run_async_streamed_worker(
                context,
                self._dependencies(context),
                self._model or settings.openai_model,
                settings.openai_api_key,
                queue,
                self._compose_streamer,
            ),
            name="coverly-qa-agent",
        )
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            if not worker.done():
                worker.cancel()
            with suppress(asyncio.CancelledError):
                await worker

    def _dependencies(self, context: QaContext) -> QaAgentDependencies:
        return QaAgentDependencies(
            context=context,
            complete=self._complete,
            official_answer=self._official_answer,
            web_search=self._web_search,
            classify_input=self._classify_input,
            classify_output=self._classify_output,
        )


def _run_streamed_worker(
    context: QaContext,
    dependencies: QaAgentDependencies,
    model: str,
    api_key: str,
    queue: Queue[QueuedAgentStreamItem],
    cancellation_requested: Event,
    compose_streamer: TextStreamer,
) -> None:
    try:
        asyncio.run(
            _run_streamed_agent(
                context,
                dependencies,
                model,
                api_key,
                queue,
                cancellation_requested,
                compose_streamer,
            )
        )
    except Exception as exc:
        enqueue_stream_item(queue, cancellation_requested, exc)
    finally:
        enqueue_stream_item(queue, cancellation_requested, None)


async def _run_async_streamed_worker(
    context: QaContext,
    dependencies: QaAgentDependencies,
    model: str,
    api_key: str,
    queue: asyncio.Queue[QueuedAgentStreamItem],
    compose_streamer: TextStreamer,
) -> None:
    cancelled = False
    try:
        await _run_async_streamed_agent(
            context,
            dependencies,
            model,
            api_key,
            queue,
            compose_streamer,
        )
    except asyncio.CancelledError:
        cancelled = True
        raise
    except Exception as exc:
        await queue.put(exc)
    finally:
        if not cancelled:
            await queue.put(None)


async def _run_streamed_agent(
    context: QaContext,
    dependencies: QaAgentDependencies,
    model: str,
    api_key: str,
    queue: Queue[QueuedAgentStreamItem],
    cancellation_requested: Event,
    compose_streamer: TextStreamer,
) -> None:
    result = Runner.run_streamed(
        create_qa_agent(model),
        input=build_agent_input(context),
        context=dependencies,
        max_turns=6,
        hooks=ProgressHooks(queue, cancellation_requested),
        run_config=_run_config(api_key),
    )
    cancellation_monitor = asyncio.create_task(
        _cancel_when_requested(result, cancellation_requested)
    )
    try:
        async for _event in result.stream_events():
            pass
    except InputGuardrailTripwireTriggered:
        _enqueue_answer_items(
            queue,
            cancellation_requested,
            out_of_scope_response(context),
            [],
            context,
            compose_streamer,
            compose=False,
        )
        return
    except OutputGuardrailTripwireTriggered:
        fallback = _unambiguous_tool_fallback(dependencies)
        if fallback is None:
            raise
        _enqueue_answer_items(
            queue, cancellation_requested, fallback, [], context, compose_streamer, compose=False
        )
        return
    finally:
        cancellation_monitor.cancel()
        with suppress(asyncio.CancelledError):
            await cancellation_monitor

    if cancellation_requested.is_set():
        return
    draft = result.final_output_as(AgentCounselorDraft, raise_if_incorrect_type=True)
    validated = _validated_or_cached_response(context, draft, dependencies)
    _enqueue_answer_items(
        queue,
        cancellation_requested,
        validated,
        list(dependencies.tool_results.values()),
        context,
        compose_streamer,
    )


async def _run_async_streamed_agent(
    context: QaContext,
    dependencies: QaAgentDependencies,
    model: str,
    api_key: str,
    queue: asyncio.Queue[QueuedAgentStreamItem],
    compose_streamer: TextStreamer,
) -> None:
    result = Runner.run_streamed(
        create_qa_agent(model),
        input=build_agent_input(context),
        context=dependencies,
        max_turns=6,
        hooks=AsyncProgressHooks(queue),
        run_config=_run_config(api_key),
    )
    try:
        async for _event in result.stream_events():
            pass
    except asyncio.CancelledError:
        result.cancel(mode="immediate")
        raise
    except InputGuardrailTripwireTriggered:
        await _put_answer_items(
            queue, out_of_scope_response(context), [], context, compose_streamer, compose=False
        )
        return
    except OutputGuardrailTripwireTriggered:
        fallback = _unambiguous_tool_fallback(dependencies)
        if fallback is None:
            raise
        await _put_answer_items(queue, fallback, [], context, compose_streamer, compose=False)
        return

    draft = result.final_output_as(AgentCounselorDraft, raise_if_incorrect_type=True)
    validated = _validated_or_cached_response(context, draft, dependencies)
    await _put_answer_items(
        queue,
        validated,
        list(dependencies.tool_results.values()),
        context,
        compose_streamer,
    )


def _enqueue_answer_items(
    queue: Queue[QueuedAgentStreamItem],
    cancellation_requested: Event,
    validated: PortfolioQuestionResponse,
    results: list[RegisteredToolResult],
    context: QaContext,
    compose_streamer: TextStreamer,
    *,
    compose: bool = True,
) -> None:
    """Compose the validated answer into stream items and enqueue them in order.

    Stops early if the consumer has cancelled — ``enqueue_stream_item`` returns
    ``False`` and no more items are pushed onto the bounded queue. Guardrail
    tripwire fallbacks pass ``compose=False`` to stream the deterministic answer
    verbatim without re-running the LLM compose.
    """

    for item in safe_answer_stream_items(
        validated, results, context.question, streamer=compose_streamer, compose=compose
    ):
        if not enqueue_stream_item(queue, cancellation_requested, item):
            return


def _next_stream_item(items: Iterator[QaAgentStreamItem]) -> QaAgentStreamItem | None:
    """Pull one item from the sync generator, mapping exhaustion to ``None``.

    Runs inside a worker thread via ``asyncio.to_thread`` so the blocking compose
    reads never execute on the ASGI event loop. ``safe_answer_stream_items`` only
    yields ``QaAgentStreamItem`` (never ``None``), so ``None`` is an unambiguous
    end sentinel.
    """

    try:
        return next(items)
    except StopIteration:
        return None


async def _put_answer_items(
    queue: asyncio.Queue[QueuedAgentStreamItem],
    validated: PortfolioQuestionResponse,
    results: list[RegisteredToolResult],
    context: QaContext,
    compose_streamer: TextStreamer,
    *,
    compose: bool = True,
) -> None:
    """Compose the validated answer OFF the event loop and put the items on the
    loop queue in ``meta → delta* → completed`` order.

    The sync ``safe_answer_stream_items`` generator drives the blocking compose
    streamer per token. Pumping it through ``asyncio.to_thread`` keeps those
    blocking network reads off the ASGI event loop, so request cancellation and
    other connections stay responsive during the compose phase. The ``await`` per
    item restores a cancellation point; ``CancelledError`` propagates out to
    terminate the worker cleanly. Guardrail tripwire fallbacks pass
    ``compose=False`` to stream the deterministic answer verbatim."""

    items = safe_answer_stream_items(
        validated, results, context.question, streamer=compose_streamer, compose=compose
    )
    while True:
        item = await asyncio.to_thread(_next_stream_item, items)
        if item is None:
            break
        await queue.put(item)


async def _cancel_when_requested(
    result: RunResultStreaming,
    cancellation_requested: Event,
) -> None:
    while not cancellation_requested.is_set():
        await asyncio.sleep(_CANCELLATION_POLL_SECONDS)

    result.cancel(mode="immediate")


def _validated_or_cached_response(
    context: QaContext,
    draft: AgentCounselorDraft,
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse:
    if dependencies.validated_response is not None:
        return dependencies.validated_response
    dependencies.validated_response = validated_agent_response(context, draft, dependencies)
    return dependencies.validated_response


def _run_config(api_key: str) -> RunConfig:
    return RunConfig(
        model_provider=OpenAIProvider(api_key=api_key),
        tracing_disabled=True,
        trace_include_sensitive_data=False,
        workflow_name="Coverly grounded QA",
    )


def _unambiguous_tool_fallback(
    dependencies: QaAgentDependencies,
) -> PortfolioQuestionResponse | None:
    results = list(dependencies.tool_results.values())
    if any(item.trust_level != "deterministic" for item in results):
        return None
    selected = select_tool_result(dependencies, None)
    return selected.response if selected is not None else None
