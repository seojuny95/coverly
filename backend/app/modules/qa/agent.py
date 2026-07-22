"""Agent definition and run wiring for the single-agent qa experiment.

This is the only file in qa/ bound to the Agents SDK -- everything else
(tools/) is plain Python so the experiment can be dropped, or the SDK
swapped, without touching it.

This version deliberately has no anti-hallucination machinery: no slot
registry, no structured output, no post-hoc backstop. Two earlier attempts
(a `{id.field:hint}` token embedded in free text, then a JSON-schema-forced
segment list) were both built on an assumption -- that the agent gets
amounts wrong often enough to need mechanical prevention -- that was never
actually measured. The structured-output version also came with a real,
documented cost: forcing a JSON schema measurably degrades reasoning
(Tam et al. 2024, "Let Me Speak Freely?", found format restrictions cut
GSM8K accuracy from 87% to 23% for one model), and in our own live eval it
produced a new failure mode (the agent looping on tool calls and never
completing) that free text never had.

So this baseline just asks the agent to quote tool results directly and
never do arithmetic itself. Whether that's actually good enough is what
evals/qa/rules.py's fact-checking now measures, before any of that
machinery gets rebuilt.

There is deliberately no separate query-rewrite step in front of this agent:
a tool call's arguments *are* the rewrite (see each tool's docstring in
tools/, which requires a self-contained argument, no "그거"/"아까 그" pronouns).
Putting rewriting before the agent was where most of counsel's measured
failures came from, because it commits to an interpretation before any tool
result is seen.
"""

from collections.abc import AsyncIterator, Callable
from functools import lru_cache
from pathlib import Path

from agents import Agent, Runner

from app.core.config import get_settings
from app.integrations.openai import ConversationMessage
from app.modules.qa.context import QaContext
from app.modules.qa.tools import ALL_TOOLS

# The instructions live next to this module as markdown because they carry the
# product position, banned phrases, and evidence-grading rules a person needs
# to read and review, per backend/PROMPTING.md's placement guidance.
_INSTRUCTIONS_PATH = Path(__file__).with_name("instructions.md")


@lru_cache(maxsize=1)
def _load_instructions() -> str:
    return _INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip()


def create_agent(model: str) -> Agent[QaContext]:
    return Agent[QaContext](
        name="Coverly QA Agent",
        model=model,
        instructions=_load_instructions(),
        tools=ALL_TOOLS,
    )


AgentStreamRunner = Callable[
    [Agent[QaContext], list[ConversationMessage], QaContext],
    AsyncIterator[str],
]


async def run_agent_streamed(
    agent: Agent[QaContext],
    conversation: list[ConversationMessage],
    context: QaContext,
) -> AsyncIterator[str]:
    """Thin, injectable wrapper around Runner.run_streamed so tests can fake it.

    Yields the agent's natural-language text delta, unmodified -- nothing
    downstream rewrites or validates it. See this module's docstring for why.
    """

    result = Runner.run_streamed(
        agent,
        input=list(conversation),
        context=context,
        max_turns=get_settings().counsel_agent_max_turns,
    )
    async for event in result.stream_events():
        if event.type != "raw_response_event":
            continue
        if event.data.type == "response.output_text.delta":
            yield event.data.delta
