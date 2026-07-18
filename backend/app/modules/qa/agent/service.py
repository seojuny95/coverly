"""User-facing QA orchestration that depends only on the Agent path."""

import logging
from collections.abc import Iterator

from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.agent.contracts import (
    QaAgentCompleted,
    QaAgentProgress,
    QaAgentRunner,
    QaAgentUnavailable,
)
from app.modules.qa.context import build_qa_context
from app.modules.qa.contracts import InsuredDemographics
from app.modules.qa.response_support import agent_unavailable_response
from app.modules.qa.schemas import ConversationMessage
from app.modules.qa.streaming import QaStreamEvent, stream_response

logger = logging.getLogger(__name__)


def stream_answer_with_agent(
    question: str,
    policies: list[PolicyInput],
    *,
    agent_runner: QaAgentRunner,
    demographics: InsuredDemographics | None = None,
    history: list[ConversationMessage] | None = None,
) -> Iterator[QaStreamEvent]:
    context = build_qa_context(question, policies, demographics, history)
    try:
        stream_agent = getattr(agent_runner, "stream", None)
        if callable(stream_agent):
            for item in stream_agent(context):
                if isinstance(item, QaAgentProgress):
                    yield {"type": "progress", "stage": item.stage, "text": item.text}
                elif isinstance(item, QaAgentCompleted):
                    yield from stream_response(item.response)
                    return
            yield from stream_response(agent_unavailable_response(context))
            return
        yield from stream_response(agent_runner.run(context))
    except QaAgentUnavailable:
        yield from stream_response(agent_unavailable_response(context))
    except Exception as exc:
        logger.warning("QA agent stream failed with %s", type(exc).__name__)
        yield from stream_response(agent_unavailable_response(context))
