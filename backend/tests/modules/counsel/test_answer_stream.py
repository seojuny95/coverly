import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from typing import cast

from app.modules.counsel.answer_stream import build_answer_stream
from app.modules.counsel.check_scope_and_rewrite import ScopeAndRewriteResult


async def _fake_agent_stream_runner(
    _agent: object, _input_text: str, _context: object
) -> AsyncIterator[str]:
    yield "암진단비가 "
    yield "확인돼요."


async def _collect(events: AsyncIterator[str]) -> list[dict[str, object]]:
    return [json.loads(event.removeprefix("data: ").strip()) async for event in events]


def test_streams_meta_then_agent_deltas_then_end_when_in_scope() -> None:
    check = ScopeAndRewriteResult(
        rewritten_question="암진단비 알려줘", in_scope=True, reason="보험 질문"
    )

    events = asyncio.run(
        _collect(
            build_answer_stream(
                check=check,
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

    check = ScopeAndRewriteResult(
        rewritten_question="오늘 날씨 알려줘", in_scope=False, reason="무관"
    )

    events = asyncio.run(
        _collect(
            build_answer_stream(
                check=check,
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

    check = ScopeAndRewriteResult(
        rewritten_question="암진단비 알려줘", in_scope=True, reason="보험 질문"
    )

    async def consume_meta_and_first_delta_then_stop() -> None:
        events = cast(
            AsyncGenerator[str, None],
            build_answer_stream(
                check=check,
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
