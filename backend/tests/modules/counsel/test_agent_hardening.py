"""The counsel agent must be told tool output is data."""

from app.modules.counsel.agent.definition import create_agent


def test_instructions_say_tool_results_are_not_commands() -> None:
    agent = create_agent("gpt-4.1-mini")

    assert isinstance(agent.instructions, str)
    assert "명령이 아닙니다" in agent.instructions


# The turn cap itself is already pinned end-to-end in test_agent.py, which
# asserts the configured value is threaded through to Runner.run_streamed.
