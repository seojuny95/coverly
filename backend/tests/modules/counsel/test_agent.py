import asyncio
from typing import Any, cast

import pytest
from agents import Runner

from app.modules.counsel.agent import create_agent, run_agent
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
    }
    assert agent.input_guardrails == []


def test_run_agent_forwards_input_and_context_to_runner_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_run(agent: object, *, input: str, context: object) -> object:
        captured["agent"] = agent
        captured["input"] = input
        captured["context"] = context
        return "fake-result"

    monkeypatch.setattr(Runner, "run", cast(Any, fake_run))

    agent = create_agent("gpt-4.1-mini")
    context = CounselContext(policies=[])
    result = asyncio.run(run_agent(agent, "암진단비 알려줘", context))

    assert cast(Any, result) == "fake-result"
    assert captured["agent"] is agent
    assert captured["input"] == "암진단비 알려줘"
    assert captured["context"] is context
