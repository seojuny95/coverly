"""SSE event contracts and stream builder for a resolved counsel answer."""

import json
from collections.abc import AsyncIterator
from typing import Literal

from pydantic import BaseModel

from app.modules.counsel.agent.definition import AgentStreamRunner, create_agent
from app.modules.counsel.check_scope_and_rewrite import ScopeAndRewriteResult
from app.modules.counsel.context import CounselContext
from app.modules.portfolio.schemas import PolicyInput

_OUT_OF_SCOPE_ANSWER = (
    "이 질문은 보험 상담 범위 밖이라 답하기 어려워요. 가입 보험, 담보, 약관, "
    "청구처럼 보험과 관련된 내용으로 물어봐 주세요."
)


class CounselMetaEvent(BaseModel):
    type: Literal["meta"] = "meta"
    in_scope: bool
    rewritten_question: str
    excluded_note: str | None


class CounselDeltaEvent(BaseModel):
    type: Literal["delta"] = "delta"
    text: str


class CounselEndEvent(BaseModel):
    type: Literal["end"] = "end"


CounselStreamEvent = CounselMetaEvent | CounselDeltaEvent | CounselEndEvent


def serialize_event(event: CounselStreamEvent) -> str:
    return f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"


async def build_answer_stream(
    *,
    check: ScopeAndRewriteResult,
    policies: list[PolicyInput],
    policy_rag_session_ids: tuple[str, ...],
    model: str,
    agent_stream_runner: AgentStreamRunner,
) -> AsyncIterator[str]:
    """Yield serialized SSE events: one meta event, then deltas, then end."""

    yield serialize_event(
        CounselMetaEvent(
            in_scope=check.in_scope,
            rewritten_question=check.rewritten_question,
            excluded_note=check.excluded_note,
        )
    )

    if not check.in_scope:
        yield serialize_event(CounselDeltaEvent(text=_OUT_OF_SCOPE_ANSWER))
        yield serialize_event(CounselEndEvent())
        return

    context = CounselContext(policies=policies, policy_rag_session_ids=policy_rag_session_ids)
    agent = create_agent(model)

    async for chunk in agent_stream_runner(agent, check.rewritten_question, context):
        yield serialize_event(CounselDeltaEvent(text=chunk))

    yield serialize_event(CounselEndEvent())
