from contextlib import contextmanager
from typing import Any

import pytest
from agents import tracing
from pydantic import SecretStr

from app.observability import agent_tracing


class _RecordingProcessor(tracing.TracingProcessor):
    def __init__(self) -> None:
        self.span_output: Any = None

    def on_trace_start(self, trace: tracing.Trace) -> None:
        return None

    def on_trace_end(self, trace: tracing.Trace) -> None:
        return None

    def on_span_start(self, span: tracing.Span[Any]) -> None:
        return None

    def on_span_end(self, span: tracing.Span[Any]) -> None:
        self.span_output = span.span_data.output

    def shutdown(self) -> None:
        return None

    def force_flush(self) -> None:
        return None


class _Settings:
    langsmith_tracing = False
    langsmith_api_key = SecretStr("")
    langsmith_endpoint = "https://api.smith.langchain.com"
    langsmith_project = "coverly-agent-test"
    langsmith_environment = "test"
    langsmith_release = "test-release"
    langsmith_tracing_sampling_rate = 0.1


class _EnabledSettings(_Settings):
    langsmith_tracing = True
    langsmith_api_key = SecretStr("test-langsmith-key")


class _ThreadSettings(_Settings):
    policy_rag_session_secret = SecretStr("thread-hash-secret")


def test_disabled_agent_tracing_removes_processors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}
    monkeypatch.setattr(agent_tracing, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        agent_tracing,
        "set_trace_processors",
        lambda processors: recorded.update(processors=processors),
    )
    monkeypatch.setattr(
        agent_tracing,
        "set_tracing_disabled",
        lambda disabled: recorded.update(disabled=disabled),
    )

    processor = agent_tracing.configure_agent_tracing()

    assert processor is None
    assert recorded == {"processors": [], "disabled": True}


def test_enabled_agent_tracing_registers_only_the_langsmith_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, Any] = {}
    delegate = _RecordingProcessor()
    monkeypatch.setattr(agent_tracing, "get_settings", lambda: _EnabledSettings())
    monkeypatch.setattr(
        agent_tracing,
        "Client",
        lambda **kwargs: recorded.update(client_kwargs=kwargs) or object(),
    )
    monkeypatch.setattr(
        agent_tracing,
        "OpenAIAgentsTracingProcessor",
        lambda **kwargs: recorded.update(delegate_kwargs=kwargs) or delegate,
    )
    monkeypatch.setattr(
        agent_tracing,
        "set_trace_processors",
        lambda processors: recorded.update(processors=processors),
    )
    monkeypatch.setattr(
        agent_tracing,
        "set_tracing_disabled",
        lambda disabled: recorded.update(disabled=disabled),
    )

    processor = agent_tracing.configure_agent_tracing()

    assert processor is delegate
    assert recorded["processors"] == [processor]
    assert recorded["disabled"] is False
    assert recorded["delegate_kwargs"]["project_name"] == "coverly-agent-test"
    assert recorded["delegate_kwargs"]["metadata"] == {
        "environment": "test",
        "release": "test-release",
        "service": "backend",
    }
    assert recorded["client_kwargs"]["api_key"] == "test-langsmith-key"
    assert "workspace_id" not in recorded["client_kwargs"]


def test_thread_id_is_stable_and_does_not_expose_session_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_tracing, "get_settings", lambda: _ThreadSettings())

    first = agent_tracing.pseudonymous_thread_id("private-session-id")
    second = agent_tracing.pseudonymous_thread_id("private-session-id")

    assert first == second
    assert first is not None
    assert first.startswith("qa-")
    assert "private-session-id" not in first


def test_agent_run_config_groups_turns_and_keeps_safe_metadata() -> None:
    config = agent_tracing.agent_run_config(thread_id="qa-thread", request_id="request-1")

    assert config.group_id == "qa-thread"
    assert config.trace_metadata == {
        "feature": "qa",
        "request_id": "request-1",
        "service": "backend",
    }


def test_agent_tool_context_adds_current_tool_span_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: dict[str, object] = {}

    @contextmanager
    def fake_tracing_context(**kwargs: object) -> Any:
        recorded.update(kwargs)
        yield

    monkeypatch.setattr(
        tracing,
        "get_current_span",
        lambda: type("Span", (), {"span_id": "tool-span-1"})(),
    )
    monkeypatch.setattr(agent_tracing, "tracing_context", fake_tracing_context)

    with agent_tracing.agent_tool_trace_context():
        pass

    assert recorded["metadata"] == {"agent_tool_span_id": "tool-span-1"}
