"""Runtime and sync-to-stream bridge for the QA agent."""

import asyncio
from collections.abc import Iterator
from queue import Queue
from threading import Thread

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    Runner,
)
from agents.models.openai_provider import OpenAIProvider

from app.core.config import get_settings
from app.integrations.openai.client import JsonCompleter
from app.modules.qa.agent.contracts import (
    AgentCounselorDraft,
    OfficialAnswerer,
    QaAgentCompleted,
    QaAgentDependencies,
    QaAgentRunner,
    QaAgentStreamItem,
    QaAgentUnavailable,
)
from app.modules.qa.agent.definition import create_qa_agent
from app.modules.qa.agent.progress import ProgressHooks, QueuedAgentStreamItem
from app.modules.qa.agent.prompt import build_agent_input
from app.modules.qa.agent.selection import select_tool_result
from app.modules.qa.agent.validation import validated_agent_response
from app.modules.qa.context import QaContext
from app.modules.qa.response_support import out_of_scope_response
from app.modules.qa.schemas import PortfolioQuestionResponse
from app.modules.qa.tools.web_search import OfficialWebSearcher, default_official_web_search


def build_qa_agent_runner(
    *,
    complete: JsonCompleter | None = None,
    classify_input: JsonCompleter | None = None,
    classify_output: JsonCompleter | None = None,
    official_answer: OfficialAnswerer | None = None,
    web_search: OfficialWebSearcher = default_official_web_search,
    model: str | None = None,
) -> QaAgentRunner:
    return OpenAiQaAgentRunner(
        complete=complete,
        classify_input=classify_input,
        classify_output=classify_output,
        official_answer=official_answer,
        web_search=web_search,
        model=model,
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
    ) -> None:
        self._complete = complete
        self._classify_input = classify_input
        self._classify_output = classify_output
        self._official_answer = official_answer
        self._web_search = web_search
        self._model = model

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
        queue: Queue[QueuedAgentStreamItem] = Queue()
        worker = Thread(
            target=_run_streamed_worker,
            args=(
                context,
                dependencies,
                self._model or settings.openai_model,
                settings.openai_api_key,
                queue,
            ),
            daemon=True,
        )
        worker.start()
        while True:
            item = queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item

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
) -> None:
    try:
        asyncio.run(_run_streamed_agent(context, dependencies, model, api_key, queue))
    except Exception as exc:
        queue.put(exc)
    finally:
        queue.put(None)


async def _run_streamed_agent(
    context: QaContext,
    dependencies: QaAgentDependencies,
    model: str,
    api_key: str,
    queue: Queue[QueuedAgentStreamItem],
) -> None:
    result = Runner.run_streamed(
        create_qa_agent(model),
        input=build_agent_input(context),
        context=dependencies,
        max_turns=6,
        hooks=ProgressHooks(queue),
        run_config=_run_config(api_key),
    )
    try:
        async for _event in result.stream_events():
            pass
    except InputGuardrailTripwireTriggered:
        queue.put(QaAgentCompleted(out_of_scope_response(context)))
        return
    except OutputGuardrailTripwireTriggered:
        fallback = _unambiguous_tool_fallback(dependencies)
        if fallback is None:
            raise
        queue.put(QaAgentCompleted(fallback))
        return
    draft = result.final_output_as(AgentCounselorDraft, raise_if_incorrect_type=True)
    queue.put(QaAgentCompleted(_validated_or_cached_response(context, draft, dependencies)))


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
