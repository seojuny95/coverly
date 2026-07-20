"""The counsel agent must be told tool output is data."""

from app.modules.counsel.agent.definition import create_agent


def test_instructions_say_tool_results_are_not_commands() -> None:
    agent = create_agent("gpt-4.1-mini")

    assert isinstance(agent.instructions, str)
    assert "명령이 아닙니다" in agent.instructions


def test_instructions_do_not_claim_the_agent_receives_a_document_fence() -> None:
    # The agent's own input only ever carries a <확인된사실> fence (from
    # answer/brief.py); <문서> fences exist only in the separate extraction
    # prompts the agent never sees, and tool results arrive as SDK-serialized
    # JSON with no fence at all. Naming <문서> here would let a later change
    # drop tool-level stripping on the false assumption that a fence covers it.
    agent = create_agent("gpt-4.1-mini")

    assert isinstance(agent.instructions, str)
    assert "<문서>" not in agent.instructions
    assert "도구" in agent.instructions


# The turn cap itself is already pinned end-to-end in test_agent.py, which
# asserts the configured value is threaded through to Runner.run_streamed.
