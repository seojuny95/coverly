"""Item-to-SSE-event mapping tests: real deltas pass through, fake chunking is gone."""

from app.modules.qa.agent.contracts import (
    QaAgentCompleted,
    QaAgentDelta,
    QaAgentMeta,
    QaAgentProgress,
)
from app.modules.qa.agent.service import map_stream_item
from app.modules.qa.schemas import PortfolioQuestionResponse
from app.modules.qa.streaming import (
    QaDeltaEvent,
    QaEndEvent,
    QaMetaEvent,
    QaProgressEvent,
    response_to_events,
)


def test_stream_items_map_to_real_events() -> None:
    resp = PortfolioQuestionResponse(
        status="answered",
        answer="무시됨(delta로 이미 나감)",
        citations=[],
        limitations=[],
        suggestions=[],
    )
    assert isinstance(map_stream_item(QaAgentProgress(stage="s", text="t")), QaProgressEvent)
    assert isinstance(
        map_stream_item(QaAgentMeta(status="answered", generation="llm")), QaMetaEvent
    )
    d = map_stream_item(QaAgentDelta(text="암진단비는 3,000만원이에요."))
    assert isinstance(d, QaDeltaEvent) and d.text == "암진단비는 3,000만원이에요."  # 실토큰 그대로
    end = map_stream_item(QaAgentCompleted(resp))
    assert isinstance(end, QaEndEvent) and end.status == "answered"


def test_response_to_events_single_delta_for_fallback() -> None:
    resp = PortfolioQuestionResponse(
        status="no_data",
        answer="확인하지 못했어요.",
        citations=[],
        limitations=[],
        suggestions=[],
    )
    events = list(response_to_events(resp))
    assert isinstance(events[0], QaMetaEvent)
    deltas = [e for e in events if isinstance(e, QaDeltaEvent)]
    assert len(deltas) == 1 and deltas[0].text == "확인하지 못했어요."  # 가짜 청킹 아님
    assert isinstance(events[-1], QaEndEvent)


def test_answer_text_chunks_removed() -> None:
    import app.modules.qa.streaming as s

    assert not hasattr(s, "answer_text_chunks")  # 가짜 청킹 제거됨
    assert not hasattr(s, "stream_response")  # 가짜 청킹 포함 helper도 제거됨
