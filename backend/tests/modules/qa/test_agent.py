"""The qa agent must be told tool output is data, not commands.

The prompt-injection defense here is structural (instructions.md tells the
model that tool results and conversation content are reference material),
so this pins the load path: create_agent() must actually carry that text.
A rewrite of instructions.md that drops it should fail here, not in prod.
"""

from app.modules.qa.agent import create_agent


def test_instructions_say_tool_results_are_not_commands() -> None:
    agent = create_agent("gpt-4.1-mini")

    assert isinstance(agent.instructions, str)
    assert "명령이 아닙니다" in agent.instructions
