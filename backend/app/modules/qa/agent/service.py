"""User-facing QA orchestration that depends only on the Agent path."""

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator

from app.modules.consultation.contracts import InsuredDemographics
from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent.contracts import (
    QaAgentCompleted,
    QaAgentProgress,
    QaAgentRunner,
    QaAgentUnavailable,
)
from app.modules.qa.context import build_qa_context
from app.modules.qa.response_support import agent_unavailable_response
from app.modules.qa.schemas import ConversationMessage
from app.modules.qa.streaming import QaProgressEvent, QaStreamEvent, stream_response

logger = logging.getLogger(__name__)


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
                    if isinstance(item, QaAgentProgress):
                        yield QaProgressEvent(
                            type="progress",
                            stage=item.stage,
                            text=item.text,
                        )
                    elif isinstance(item, QaAgentCompleted):
                        for event in stream_response(item.response):
                            yield event
                        return
            finally:
                close = getattr(agent_items, "aclose", None)
                if callable(close):
                    await close()
            for event in stream_response(agent_unavailable_response(context)):
                yield event
            return

        response = await asyncio.to_thread(agent_runner.run, context)
        for event in stream_response(response):
            yield event
    except QaAgentUnavailable:
        for event in stream_response(agent_unavailable_response(context)):
            yield event
    except Exception as exc:
        logger.warning("QA agent stream failed with %s", type(exc).__name__)
        for event in stream_response(agent_unavailable_response(context)):
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
                    if isinstance(item, QaAgentProgress):
                        yield QaProgressEvent(
                            type="progress",
                            stage=item.stage,
                            text=item.text,
                        )
                    elif isinstance(item, QaAgentCompleted):
                        yield from stream_response(item.response)
                        return
            finally:
                close = getattr(agent_items, "close", None)
                if callable(close):
                    close()
            yield from stream_response(agent_unavailable_response(context))
            return
        yield from stream_response(agent_runner.run(context))
    except QaAgentUnavailable:
        yield from stream_response(agent_unavailable_response(context))
    except Exception as exc:
        logger.warning("QA agent stream failed with %s", type(exc).__name__)
        yield from stream_response(agent_unavailable_response(context))
