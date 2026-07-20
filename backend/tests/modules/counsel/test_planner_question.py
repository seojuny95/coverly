import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.modules.counsel.answer import build_answer_stream
from app.modules.counsel.planner import CounselPlan


def _plan(**overrides: object) -> CounselPlan:
    base: dict[str, object] = {
        "question_without_history": "이번 질문만 정리한 문장",
        "rewritten_question": "이전 대화로 복원한 문장",
        "needs_history": False,
        "in_scope": True,
        "reason": "보험 질문",
    }
    return CounselPlan.model_validate(base | overrides)


def test_a_self_contained_question_ignores_the_history_resolved_rewrite() -> None:
    # The planner can quietly replace an off-topic question with an earlier one.
    # When it says the turn stands on its own, the version written without any
    # history is the one to answer -- it cannot have borrowed from an old topic.
    plan = _plan(needs_history=False)

    assert plan.question_to_answer == "이번 질문만 정리한 문장"


def test_a_question_that_points_backwards_uses_the_resolved_rewrite() -> None:
    plan = _plan(needs_history=True)

    assert plan.question_to_answer == "이전 대화로 복원한 문장"


def test_an_out_of_scope_turn_keeps_its_own_question() -> None:
    plan = _plan(
        needs_history=False,
        in_scope=False,
        question_without_history="오늘 서울 날씨 어때?",
        rewritten_question="교통사고처리지원금 얼마야?",
    )

    assert plan.question_to_answer == "오늘 서울 날씨 어때?"


def test_the_agent_is_asked_the_self_contained_question_not_the_resolved_rewrite() -> None:
    # The motivating bug end to end: a topic change the planner still judged
    # in scope, whose rewrite had swallowed the previous turn's question.
    asked: list[str] = []

    async def capture_runner(_agent: Any, conversation: Any, _context: Any) -> AsyncIterator[str]:
        asked.append(str(conversation[-1]["content"]))
        yield "답변"

    plan = _plan(
        needs_history=False,
        question_without_history="면책기간이 뭐야?",
        rewritten_question="암진단비(유사암제외) 얼마야?",
    )

    events = asyncio.run(
        _collect(
            build_answer_stream(
                question="면책기간이 뭐야?",
                history=[],
                plan=plan,
                policies=[],
                policy_rag_session_ids=(),
                model="gpt-4.1-mini",
                turns_remaining=9,
                agent_stream_runner=capture_runner,
            )
        )
    )

    assert "면책기간" in asked[0]
    assert "암진단비" not in asked[0]
    assert events[0]["rewritten_question"] == "면책기간이 뭐야?"


async def _collect(events: AsyncIterator[str]) -> list[dict[str, Any]]:
    return [json.loads(event.removeprefix("data: ").strip()) async for event in events]
