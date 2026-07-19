"""Agent definition and run wiring for grounded insurance counseling."""

from collections.abc import Awaitable, Callable

from agents import Agent, Runner, RunResult

from app.modules.counsel.context import CounselContext
from app.modules.counsel.tools.coverages import find_coverages, list_coverage_names
from app.modules.counsel.tools.policies import list_policies

_INSTRUCTIONS = """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 보험 상담사입니다.

- 특정 상품 가입, 해지, 증액을 지시하지 않습니다.
- 보상 가능 여부, 면책, 지급액을 단정하지 않습니다.
- 근거 밖의 담보, 금액, 조건을 지어내지 않습니다."""


def create_agent(model: str) -> Agent[CounselContext]:
    return Agent[CounselContext](
        name="Coverly Counsel Agent",
        model=model,
        instructions=_INSTRUCTIONS,
        tools=[list_policies, list_coverage_names, find_coverages],
    )


AgentRunner = Callable[[Agent[CounselContext], str, CounselContext], Awaitable[RunResult]]


async def run_agent(
    agent: Agent[CounselContext],
    input_text: str,
    context: CounselContext,
) -> RunResult:
    """Thin, injectable wrapper around Runner.run so tests can fake it."""

    return await Runner.run(agent, input=input_text, context=context)
