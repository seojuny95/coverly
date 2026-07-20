import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agents import Runner

from app.modules.counsel.agent.definition import create_agent, run_agent_streamed
from app.modules.counsel.context import CounselContext


def test_create_agent_has_tools_and_no_native_guardrails() -> None:
    # Scope-checking already happens in the router before the agent runs, so
    # the SDK's native input_guardrails mechanism is intentionally unused.
    agent = create_agent("gpt-4.1-mini")

    assert agent.name == "Coverly Counsel Agent"
    assert agent.model == "gpt-4.1-mini"
    assert {tool.name for tool in agent.tools} == {
        "list_policies",
        "list_coverage_names",
        "find_coverages",
        "calculate_coverage_total",
        "find_overlapping_coverages",
        "get_claim_channels",
        "retrieve_official_guidance",
        "retrieve_policy_terms",
    }
    assert agent.input_guardrails == []


def test_create_agent_tells_the_model_not_to_mix_amounts_across_sources() -> None:
    agent = create_agent("gpt-4.1-mini")

    instructions = cast(str, agent.instructions)
    assert "섞어 쓰지 않습니다" in instructions


def test_run_agent_streamed_yields_only_text_deltas_and_forwards_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeStreamingResult:
        async def stream_events(self) -> AsyncIterator[object]:
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(type="response.output_text.delta", delta="안녕"),
            )
            # Non-text raw events and other event kinds must be skipped, not yielded.
            yield SimpleNamespace(type="agent_updated_stream_event")
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(type="response.completed"),
            )
            yield SimpleNamespace(
                type="raw_response_event",
                data=SimpleNamespace(type="response.output_text.delta", delta="하세요"),
            )

    def fake_run_streamed(
        agent: object, *, input: str, context: object, max_turns: object = None
    ) -> object:
        captured["agent"] = agent
        captured["input"] = input
        captured["context"] = context
        captured["max_turns"] = max_turns
        return _FakeStreamingResult()

    monkeypatch.setattr(Runner, "run_streamed", cast(Any, fake_run_streamed))

    agent = create_agent("gpt-4.1-mini")
    context = CounselContext(policies=[])

    async def collect() -> list[str]:
        return [chunk async for chunk in run_agent_streamed(agent, "암진단비 알려줘", context)]

    chunks = asyncio.run(collect())

    assert chunks == ["안녕", "하세요"]
    assert captured["agent"] is agent
    assert captured["input"] == "암진단비 알려줘"
    assert captured["context"] is context
