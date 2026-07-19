"""Agent definition and run wiring for grounded insurance counseling."""

from collections.abc import Awaitable, Callable

from agents import Agent, Runner, RunResult

from app.modules.counsel.context import CounselContext
from app.modules.counsel.tools.claims import get_claim_channels
from app.modules.counsel.tools.coverages import (
    calculate_coverage_total,
    find_coverages,
    find_overlapping_coverages,
    list_coverage_names,
)
from app.modules.counsel.tools.official import retrieve_official_guidance
from app.modules.counsel.tools.policies import list_policies
from app.modules.counsel.tools.policy_terms import retrieve_policy_terms

_INSTRUCTIONS = """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 보험 상담사입니다.

- 특정 상품 가입, 해지, 증액을 지시하지 않습니다.
- 보상 가능 여부, 면책, 지급액을 단정하지 않습니다.
- 근거 밖의 담보, 금액, 조건을 지어내지 않습니다.
- retrieve_official_guidance의 일반 기준과 retrieve_policy_terms·구조화 도구로 확인한
  사용자의 실제 계약 사실을 구분해서 말합니다. 일반 기준을 사용자의 확정된 계약
  조건인 것처럼 말하지 않습니다.
- 여러 도구 결과를 합쳐 답할 때, 각 금액은 반드시 그 금액이 속한 담보·보험사에만
  붙여서 말합니다. 서로 다른 담보나 보험사의 금액을 섞어 쓰지 않습니다."""


def create_agent(model: str) -> Agent[CounselContext]:
    return Agent[CounselContext](
        name="Coverly Counsel Agent",
        model=model,
        instructions=_INSTRUCTIONS,
        tools=[
            list_policies,
            list_coverage_names,
            find_coverages,
            calculate_coverage_total,
            find_overlapping_coverages,
            get_claim_channels,
            retrieve_official_guidance,
            retrieve_policy_terms,
        ],
    )


AgentRunner = Callable[[Agent[CounselContext], str, CounselContext], Awaitable[RunResult]]


async def run_agent(
    agent: Agent[CounselContext],
    input_text: str,
    context: CounselContext,
) -> RunResult:
    """Thin, injectable wrapper around Runner.run so tests can fake it."""

    return await Runner.run(agent, input=input_text, context=context)
