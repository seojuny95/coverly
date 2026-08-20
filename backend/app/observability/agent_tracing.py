"""LangSmith integration for the OpenAI Agents SDK."""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from agents import RunConfig, set_trace_processors, set_tracing_disabled, tracing
from langsmith import Client, tracing_context
from langsmith.integrations.openai_agents_sdk import OpenAIAgentsTracingProcessor

from app.core.config import get_settings
from app.observability.sanitization import sanitize_trace_payload

logger = logging.getLogger(__name__)

_TRACE_THREAD_PREFIX = "qa-"


def configure_agent_tracing() -> tracing.TracingProcessor | None:
    """Configure one LangSmith processor and disable the SDK's default exporter."""

    settings = get_settings()
    api_key = settings.langsmith_api_key.get_secret_value()
    if not settings.langsmith_tracing:
        set_trace_processors([])
        set_tracing_disabled(True)
        return None

    if not api_key or not settings.langsmith_endpoint or not settings.langsmith_project:
        set_trace_processors([])
        set_tracing_disabled(True)
        logger.warning("langsmith_tracing_configuration_incomplete")
        return None

    client = Client(
        api_key=api_key,
        api_url=settings.langsmith_endpoint,
        hide_inputs=sanitize_trace_payload,
        hide_outputs=sanitize_trace_payload,
        hide_metadata=sanitize_trace_payload,
        tracing_sampling_rate=settings.langsmith_tracing_sampling_rate,
        omit_traced_runtime_info=True,
    )
    processor = cast(
        tracing.TracingProcessor,
        OpenAIAgentsTracingProcessor(  # type: ignore[no-untyped-call]
            client=client,
            project_name=settings.langsmith_project,
            name="coverly.agent",
            tags=["agent", "qa"],
            metadata={
                "environment": settings.langsmith_environment,
                "release": settings.langsmith_release,
                "service": "backend",
            },
        ),
    )
    set_trace_processors([processor])
    set_tracing_disabled(False)
    return processor


def shutdown_agent_tracing(
    processor: tracing.TracingProcessor | None,
) -> None:
    """Flush pending traces without making application shutdown depend on LangSmith."""

    if processor is None:
        return
    try:
        processor.force_flush()
    except Exception as exc:
        logger.warning(
            "langsmith_agent_trace_flush_failed",
            extra={"error_type": type(exc).__name__},
        )


def pseudonymous_thread_id(session_id: str) -> str | None:
    """Create a stable LangSmith thread ID without exporting the session ID."""

    secret = get_settings().policy_rag_session_secret.get_secret_value()
    if not session_id or not secret:
        return None
    digest = hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
    return f"{_TRACE_THREAD_PREFIX}{digest}"


def agent_run_config(*, thread_id: str | None, request_id: str) -> RunConfig:
    """Build safe per-turn metadata for the Agents SDK trace."""

    return RunConfig(
        workflow_name="Coverly QA workflow",
        group_id=thread_id,
        trace_metadata={
            "feature": "qa",
            "request_id": request_id,
            "service": "backend",
        },
    )


@contextmanager
def agent_tool_trace_context() -> Iterator[None]:
    """Correlate nested LangSmith RAG runs with the active Agents SDK tool span."""

    span = tracing.get_current_span()
    metadata = {"agent_tool_span_id": span.span_id} if span is not None else None
    with tracing_context(metadata=metadata):
        yield
