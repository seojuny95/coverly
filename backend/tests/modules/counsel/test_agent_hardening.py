"""The counsel agent must be told tool output is data, and must not loop forever."""

from app.core.config import get_settings
from app.modules.counsel.agent.definition import create_agent


def test_instructions_say_tool_results_are_not_commands() -> None:
    agent = create_agent("gpt-4.1-mini")

    assert isinstance(agent.instructions, str)
    assert "명령이 아닙니다" in agent.instructions


def test_agent_turn_cap_is_configured() -> None:
    assert get_settings().counsel_agent_max_turns >= 1
