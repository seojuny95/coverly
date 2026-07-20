import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from typing import cast

from app.modules.counsel.answer import build_answer_stream
from app.modules.counsel.planner import CounselPlan, CounselTask
from app.modules.portfolio.schemas import PolicyInput


async def _fake_agent_stream_runner(
    _agent: object, _input_text: str, _context: object
) -> AsyncIterator[str]:
    yield "암진단비가 "
    yield "확인돼요."


async def _collect(events: AsyncIterator[str]) -> list[dict[str, object]]:
    return [json.loads(event.removeprefix("data: ").strip()) async for event in events]


def test_streams_meta_then_agent_deltas_then_end_when_in_scope() -> None:
    check = CounselPlan(rewritten_question="암진단비 알려줘", in_scope=True, reason="보험 질문")

    events = asyncio.run(
        _collect(
            build_answer_stream(
                question=check.rewritten_question,
                plan=check,
                policies=[],
                policy_rag_session_ids=(),
                model="gpt-4.1-mini",
                agent_stream_runner=_fake_agent_stream_runner,
            )
        )
    )

    assert events == [
        {
            "type": "meta",
            "in_scope": True,
            "rewritten_question": "암진단비 알려줘",
            "excluded_note": None,
        },
        {"type": "delta", "text": "암진단비가 "},
        {"type": "delta", "text": "확인돼요."},
        {"type": "end"},
    ]


def test_streams_the_refusal_message_without_running_the_agent_when_out_of_scope() -> None:
    called = False

    async def unexpected_runner(
        _agent: object, _input_text: str, _context: object
    ) -> AsyncIterator[str]:
        nonlocal called
        called = True
        yield "should not run"

    check = CounselPlan(rewritten_question="오늘 날씨 알려줘", in_scope=False, reason="무관")

    events = asyncio.run(
        _collect(
            build_answer_stream(
                question=check.rewritten_question,
                plan=check,
                policies=[],
                policy_rag_session_ids=(),
                model="gpt-4.1-mini",
                agent_stream_runner=unexpected_runner,
            )
        )
    )

    assert events[0]["type"] == "meta"
    assert events[0]["in_scope"] is False
    assert events[1]["type"] == "delta"
    assert events[-1] == {"type": "end"}
    assert called is False


def test_streams_fact_answer_without_running_agent_for_fact_only_plan() -> None:
    called = False

    async def unexpected_runner(
        _agent: object, _input_text: str, _context: object
    ) -> AsyncIterator[str]:
        nonlocal called
        called = True
        yield "should not run"

    check = CounselPlan(
        rewritten_question="가입한 보험 몇 개야?",
        in_scope=True,
        reason="보험 개수 질문",
        tasks=[CounselTask(kind="policy_count")],
        response_mode="fact_only",
    )

    events = asyncio.run(
        _collect(
            build_answer_stream(
                question=check.rewritten_question,
                plan=check,
                policies=[
                    PolicyInput.model_validate(
                        {"id": "p1", "기본정보": {"보험사": "현대해상"}, "보장목록": []}
                    ),
                    PolicyInput.model_validate(
                        {"id": "p2", "기본정보": {"보험사": "삼성화재"}, "보장목록": []}
                    ),
                ],
                policy_rag_session_ids=(),
                model="gpt-4.1-mini",
                agent_stream_runner=unexpected_runner,
            )
        )
    )

    assert events[1] == {"type": "delta", "text": "현재 업로드된 보험은 2건이에요."}
    assert events[-1] == {"type": "end"}
    assert called is False


def test_streams_fact_answer_before_agent_for_fact_then_explanation_plan() -> None:
    check = CounselPlan(
        rewritten_question="암진단비 얼마고 무슨 뜻이야?",
        in_scope=True,
        reason="담보 사실과 설명 질문",
        tasks=[CounselTask(kind="coverage_lookup", coverage_names=["암진단비"])],
        response_mode="fact_then_explanation",
    )

    events = asyncio.run(
        _collect(
            build_answer_stream(
                question=check.rewritten_question,
                plan=check,
                policies=[
                    PolicyInput.model_validate(
                        {
                            "id": "p1",
                            "기본정보": {"보험사": "현대해상", "상품명": "건강보험A"},
                            "보장목록": [
                                {
                                    "담보명": "암진단비",
                                    "가입금액": "3,000만원",
                                    "가입금액숫자": 30_000_000,
                                    "지급유형": "정액",
                                    "해설": "암 진단 시 정액 보장을 확인하는 담보예요.",
                                }
                            ],
                        }
                    )
                ],
                policy_rag_session_ids=(),
                model="gpt-4.1-mini",
                agent_stream_runner=_fake_agent_stream_runner,
            )
        )
    )

    assert events[1]["type"] == "delta"
    assert "암진단비: 3,000만원" in str(events[1]["text"])
    assert events[2] == {"type": "delta", "text": "암진단비가 "}
    assert events[-1] == {"type": "end"}


def test_closing_the_stream_early_propagates_into_the_agent_stream_runner() -> None:
    # Guards SSE-disconnect cancellation from silently breaking (e.g. buffering, detached tasks).
    cleaned_up = False

    async def slow_agent_stream_runner(
        _agent: object, _input_text: str, _context: object
    ) -> AsyncIterator[str]:
        nonlocal cleaned_up
        try:
            yield "첫 "
            yield "이 청크는 소비되지 않아야 함"
        finally:
            cleaned_up = True

    check = CounselPlan(rewritten_question="암진단비 알려줘", in_scope=True, reason="보험 질문")

    async def consume_meta_and_first_delta_then_stop() -> None:
        events = cast(
            AsyncGenerator[str, None],
            build_answer_stream(
                question=check.rewritten_question,
                plan=check,
                policies=[],
                policy_rag_session_ids=(),
                model="gpt-4.1-mini",
                agent_stream_runner=slow_agent_stream_runner,
            ),
        )
        seen = 0
        async for _event in events:
            seen += 1
            if seen == 2:  # meta event, then the first delta
                break
        await events.aclose()

    asyncio.run(consume_meta_and_first_delta_then_stop())

    assert cleaned_up is True
