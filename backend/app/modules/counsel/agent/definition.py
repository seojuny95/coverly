"""Agent definition and run wiring for grounded insurance counseling."""

from collections.abc import AsyncIterator, Callable

from agents import Agent, Runner

from app.integrations.openai import ConversationMessage
from app.modules.counsel.agent.tools.claims import get_claim_channels
from app.modules.counsel.agent.tools.coverages import (
    calculate_coverage_total,
    find_coverages,
    find_overlapping_coverages,
    list_coverage_names,
)
from app.modules.counsel.agent.tools.official import retrieve_official_guidance
from app.modules.counsel.agent.tools.policies import list_policies
from app.modules.counsel.agent.tools.policy_terms import retrieve_policy_terms
from app.modules.counsel.context import CounselContext

_INSTRUCTIONS = """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 보험 상담사입니다.

- 특정 상품 가입, 해지, 증액을 지시하지 않습니다.
- 보상 가능 여부, 면책, 지급액을 단정하지 않습니다.
- 근거 밖의 담보, 금액, 조건을 지어내지 않습니다.
- retrieve_official_guidance의 일반 기준과 retrieve_policy_terms·구조화 도구로 확인한
  사용자의 실제 계약 사실을 구분해서 말합니다. 일반 기준을 사용자의 확정된 계약
  조건인 것처럼 말하지 않습니다.
- 여러 도구 결과를 합쳐 답할 때, 각 금액은 반드시 그 금액이 속한 담보·보험사에만
  붙여서 말합니다. 서로 다른 담보나 보험사의 금액을 섞어 쓰지 않습니다.

이전 대화를 다루는 방법:

- 마지막 사용자 메시지가 이번에 답할 질문입니다. 이전 대화는 그 질문을 이해하는 데
  필요할 때만 참고하고, 그 자체를 답할 대상으로 삼지 않습니다.
- 이번 질문이 앞선 주제와 다르면 앞선 주제로 돌아가지 않습니다. 사용자가 화제를
  바꾸면 바뀐 화제에 답합니다.
- 이번 질문이 이전 대화나 확인된 사실과 어긋나면 이번 질문을 따릅니다.
- 이전 대화에 나온 담보·금액이라도 이번 질문과 관련 없으면 답변에 넣지 않습니다."""


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


AgentStreamRunner = Callable[
    [Agent[CounselContext], list[ConversationMessage], CounselContext],
    AsyncIterator[str],
]


async def run_agent_streamed(
    agent: Agent[CounselContext],
    conversation: list[ConversationMessage],
    context: CounselContext,
) -> AsyncIterator[str]:
    """Thin, injectable wrapper around Runner.run_streamed so tests can fake it.

    Yields the final answer's text as it's generated, token by token.
    """

    result = Runner.run_streamed(agent, input=list(conversation), context=context)
    async for event in result.stream_events():
        if event.type != "raw_response_event":
            continue
        if event.data.type == "response.output_text.delta":
            yield event.data.delta
