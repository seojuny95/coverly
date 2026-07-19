"""User-facing QA orchestration that depends only on the Agent path."""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from typing import cast

from app.core.generation import GenerationMode
from app.modules.consultation.contracts import InsuredDemographics
from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent.contracts import (
    QaAgentCompleted,
    QaAgentDelta,
    QaAgentMeta,
    QaAgentProgress,
    QaAgentRunner,
    QaAgentStreamItem,
    QaAgentUnavailable,
)
from app.modules.qa.context import build_qa_context
from app.modules.qa.response_support import agent_unavailable_response
from app.modules.qa.schemas import ConversationMessage, QaAnswerStatus
from app.modules.qa.streaming import (
    QaDeltaEvent,
    QaEndEvent,
    QaMetaEvent,
    QaProgressEvent,
    QaStreamEvent,
    response_to_events,
)

logger = logging.getLogger(__name__)


def map_stream_item(item: QaAgentStreamItem) -> QaStreamEvent | None:
    """Map a single runtime stream item to its wire-level SSE event.

    ``QaAgentDelta`` carries the runtime's real, verified token text through
    unchanged — there is no re-chunking here.
    """

    if isinstance(item, QaAgentProgress):
        return QaProgressEvent(type="progress", stage=item.stage, text=item.text)
    if isinstance(item, QaAgentMeta):
        return QaMetaEvent(
            type="meta",
            status=cast(QaAnswerStatus, item.status),
            generation=cast(GenerationMode, item.generation),
        )
    if isinstance(item, QaAgentDelta):
        return QaDeltaEvent(type="delta", text=item.text)
    if isinstance(item, QaAgentCompleted):
        response = item.response
        return QaEndEvent(
            type="end",
            status=response.status,
            generation=response.generation,
            citations=response.citations,
            limitations=response.limitations,
            suggestions=response.suggestions,
            claim_channels=response.claim_channels,
        )
    return None


async def stream_answer_with_agent_async(
    question: str,
    policies: list[PolicyInput],
    *,
    agent_runner: QaAgentRunner,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
    policy_rag_session_ids: tuple[str, ...] = (),
) -> AsyncIterator[QaStreamEvent]:
    """Stream through the request loop so ASGI cancellation reaches the agent."""

    context = build_qa_context(
        question,
        policies,
        demographics,
        history,
        policy_rag_session_ids=policy_rag_session_ids,
    )
    try:
        stream_agent = getattr(agent_runner, "astream", None)
        if callable(stream_agent):
            agent_items = stream_agent(context)
            try:
                async for item in agent_items:
                    event = map_stream_item(item)
                    if event is not None:
                        yield event
                    if isinstance(item, QaAgentCompleted):
                        return
            finally:
                close = getattr(agent_items, "aclose", None)
                if callable(close):
                    await close()
            for event in response_to_events(agent_unavailable_response(context)):
                yield event
            return

        response = await asyncio.to_thread(agent_runner.run, context)
        for event in response_to_events(response):
            yield event
    except QaAgentUnavailable:
        for event in response_to_events(agent_unavailable_response(context)):
            yield event
    except Exception as exc:
        logger.warning("QA agent stream failed with %s", type(exc).__name__)
        for event in response_to_events(agent_unavailable_response(context)):
            yield event


def stream_answer_with_agent(
    question: str,
    policies: list[PolicyInput],
    *,
    agent_runner: QaAgentRunner,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
    policy_rag_session_ids: tuple[str, ...] = (),
) -> Iterator[QaStreamEvent]:
    context = build_qa_context(
        question,
        policies,
        demographics,
        history,
        policy_rag_session_ids=policy_rag_session_ids,
    )
    try:
        stream_agent = getattr(agent_runner, "stream", None)
        if callable(stream_agent):
            agent_items = stream_agent(context)
            try:
                for item in agent_items:
                    event = map_stream_item(item)
                    if event is not None:
                        yield event
                    if isinstance(item, QaAgentCompleted):
                        return
            finally:
                close = getattr(agent_items, "close", None)
                if callable(close):
                    close()
            yield from response_to_events(agent_unavailable_response(context))
            return
        yield from response_to_events(agent_runner.run(context))
    except QaAgentUnavailable:
        yield from response_to_events(agent_unavailable_response(context))
    except Exception as exc:
        logger.warning("QA agent stream failed with %s", type(exc).__name__)
        yield from response_to_events(agent_unavailable_response(context))
