"""Behavior tests for the stream-item generator (meta → deltas → completed)."""

from collections.abc import Iterator

from app.modules.consultation.contracts import ConsultationEvidence
from app.modules.qa.agent.answer_stream import answer_stream_items, safe_answer_stream_items
from app.modules.qa.agent.contracts import (
    QaAgentCompleted,
    QaAgentDelta,
    QaAgentMeta,
    RegisteredToolResult,
)
from app.modules.qa.schemas import PortfolioQuestionResponse


def _res(answer: str, *ev: ConsultationEvidence) -> RegisteredToolResult:
    return RegisteredToolResult(
        kind="coverage_total",
        response=PortfolioQuestionResponse(
            status="answered", answer=answer, citations=[], limitations=[]
        ),
        evidence=tuple(ev),
        trust_level="deterministic",
    )


def test_situational_flag_reaches_compose_prompt() -> None:
    validated = PortfolioQuestionResponse(
        status="answered",
        answer="암진단비와 암수술비가 확인돼요.",
        citations=[],
        limitations=[],
        generation="llm",
    )
    captured: dict[str, str] = {}

    def capturing_streamer(system: str, user: str) -> Iterator[str]:
        captured["user"] = user
        yield "확인된 관련 보장을 안내드려요."

    list(
        answer_stream_items(
            validated,
            [],
            "대장암에 걸렸는데 어떻게 해?",
            streamer=capturing_streamer,
            situational=True,
        )
    )

    assert "되묻" in captured["user"]  # 상황형 되묻기 규정이 compose 프롬프트까지 전달됨
    assert "보유" in captured["user"]


def test_non_situational_flag_keeps_plain_compose_prompt() -> None:
    validated = PortfolioQuestionResponse(
        status="answered",
        answer="암진단비가 확인돼요.",
        citations=[],
        limitations=[],
        generation="llm",
    )
    captured: dict[str, str] = {}

    def capturing_streamer(system: str, user: str) -> Iterator[str]:
        captured["user"] = user
        yield "암진단비가 확인돼요."

    list(
        answer_stream_items(
            validated,
            [],
            "암진단비 알려줘",
            streamer=capturing_streamer,
        )
    )

    assert "되묻" not in captured["user"]


def test_grounded_streams_meta_then_verified_deltas_then_completed() -> None:
    r = _res(
        "암진단비 30,000,000원",
        ConsultationEvidence(
            id="c1", fact="암진단비 30,000,000원", coverage_name="암진단비", amount=30_000_000
        ),
    )
    validated = PortfolioQuestionResponse(
        status="answered",
        answer="암진단비는 30,000,000원이 확인돼요.",
        citations=[],
        limitations=[],
    )

    # fake tokens the compose step would emit using the placeholder
    def fake(system: str, user: str) -> Iterator[str]:
        yield from ["암진단비는 ", "{{amt1}}", "이 있어요."]

    items = list(answer_stream_items(validated, [r], "암보장?", streamer=fake))
    assert isinstance(items[0], QaAgentMeta) and items[0].status == "answered"
    deltas = [i.text for i in items if isinstance(i, QaAgentDelta)]
    assert "".join(deltas) == "암진단비는 30,000,000원이 있어요."  # placeholder substituted
    assert "30,000,000" in "".join(deltas)  # confirmed value exposed
    assert isinstance(items[-1], QaAgentCompleted)


def test_fixed_refusal_streams_single_delta_of_validated_answer() -> None:
    validated = PortfolioQuestionResponse(
        status="no_data", answer="확인하지 못했어요.", citations=[], limitations=[]
    )

    def fake(system: str, user: str) -> Iterator[str]:  # must not be called
        raise AssertionError("compose must not run for fixed refusal")
        yield ""

    items = list(answer_stream_items(validated, [], "질문", streamer=fake))
    assert isinstance(items[0], QaAgentMeta)
    deltas = [i.text for i in items if isinstance(i, QaAgentDelta)]
    assert deltas == ["확인하지 못했어요."]
    assert isinstance(items[-1], QaAgentCompleted)


def test_fabricated_number_from_compose_is_withheld() -> None:
    r = _res(
        "암진단비 30,000,000원",
        ConsultationEvidence(
            id="c1", fact="암진단비 30,000,000원", coverage_name="암진단비", amount=30_000_000
        ),
    )
    validated = PortfolioQuestionResponse(
        status="answered", answer="암진단비는 30,000,000원이에요.", citations=[], limitations=[]
    )

    def fake(system: str, user: str) -> Iterator[str]:  # model invents a number
        yield from ["합계는 ", "9,999만원", "이에요."]

    # via the safe wrapper: every sentence fails verification, so the wrapper
    # degrades to validated.answer instead of leaving the user with nothing.
    items = list(safe_answer_stream_items(validated, [r], "질문", streamer=fake))
    deltas = "".join(i.text for i in items if isinstance(i, QaAgentDelta))
    assert "9,999" not in deltas  # sentence verification still blocks the fabricated number
    assert deltas == validated.answer  # degrades to the safe validated answer, not silence


def test_safe_wrapper_degrades_when_compose_withholds_all_sentences() -> None:
    """When every composed sentence fails verification, the safe wrapper must
    not complete with zero deltas — it degrades to validated.answer, same as
    the exception path, so the user is never left with a silently empty
    answer."""
    r = _res(
        "암진단비 30,000,000원",
        ConsultationEvidence(
            id="c1", fact="암진단비 30,000,000원", coverage_name="암진단비", amount=30_000_000
        ),
    )
    validated = PortfolioQuestionResponse(
        status="answered", answer="암진단비는 30,000,000원이에요.", citations=[], limitations=[]
    )

    def fake(system: str, user: str) -> Iterator[str]:  # model invents an ungrounded number
        yield from ["합계는 ", "9,999만원", "이에요."]

    items = list(safe_answer_stream_items(validated, [r], "질문", streamer=fake))
    assert isinstance(items[0], QaAgentMeta)
    assert isinstance(items[-1], QaAgentCompleted)
    deltas = [i.text for i in items if isinstance(i, QaAgentDelta)]
    assert deltas  # must not be silently empty
    assert "".join(deltas) == validated.answer
    assert "9,999" not in "".join(deltas)


def test_general_guidance_with_no_amounts_streams_fine() -> None:
    """Composable general_guidance (answered, no tool results) streams cleanly
    when the compose text carries no numbers to verify."""
    validated = PortfolioQuestionResponse(
        status="answered",
        answer="약관을 함께 확인해보면 좋아요.",
        citations=[],
        limitations=[],
        generation="llm",
    )

    def fake(system: str, user: str) -> Iterator[str]:
        yield from ["약관을 함께 ", "확인해보면 ", "좋아요."]

    items = list(answer_stream_items(validated, [], "질문", streamer=fake))
    assert isinstance(items[0], QaAgentMeta)
    assert items[0].generation == "llm"
    deltas = "".join(i.text for i in items if isinstance(i, QaAgentDelta))
    assert deltas == "약관을 함께 확인해보면 좋아요."
    assert isinstance(items[-1], QaAgentCompleted)


def test_compose_sentence_with_unknown_placeholder_is_withheld() -> None:
    """An unknown placeholder label fails closed — the whole sentence is dropped,
    even though a valid sentence around it still streams."""
    r = _res(
        "암진단비 30,000,000원",
        ConsultationEvidence(
            id="c1", fact="암진단비 30,000,000원", coverage_name="암진단비", amount=30_000_000
        ),
    )
    validated = PortfolioQuestionResponse(
        status="answered", answer="암진단비는 30,000,000원이에요.", citations=[], limitations=[]
    )

    def fake(system: str, user: str) -> Iterator[str]:
        yield from ["암진단비는 ", "{{amt1}}", "이에요. ", "추가는 ", "{{unknown}}", "이에요."]

    items = list(answer_stream_items(validated, [r], "질문", streamer=fake))
    deltas = "".join(i.text for i in items if isinstance(i, QaAgentDelta))
    assert "30,000,000원이에요." in deltas  # known placeholder released
    assert "{{" not in deltas and "unknown" not in deltas  # unknown label withheld


def test_safe_wrapper_degrades_to_validated_on_compose_exception() -> None:
    r = _res(
        "암진단비 30,000,000원",
        ConsultationEvidence(
            id="c1", fact="암진단비 30,000,000원", coverage_name="암진단비", amount=30_000_000
        ),
    )
    validated = PortfolioQuestionResponse(
        status="answered", answer="암진단비는 30,000,000원이에요.", citations=[], limitations=[]
    )

    def boom(system: str, user: str) -> Iterator[str]:
        raise RuntimeError("compose failed")
        yield ""

    items = list(safe_answer_stream_items(validated, [r], "질문", streamer=boom))
    assert isinstance(items[0], QaAgentMeta)
    assert isinstance(items[-1], QaAgentCompleted)
    deltas = "".join(i.text for i in items if isinstance(i, QaAgentDelta))
    assert deltas == "암진단비는 30,000,000원이에요."  # degrade to safe validated answer


def test_verbatim_fallback_streams_single_delta_without_calling_compose() -> None:
    """A deterministic tripwire fallback (``compose=False``) must emit the
    validated answer verbatim — meta → single delta → completed — and never
    invoke the compose streamer, even though the mode would otherwise compose."""
    r = _res(
        "암진단비 30,000,000원",
        ConsultationEvidence(
            id="c1", fact="암진단비 30,000,000원", coverage_name="암진단비", amount=30_000_000
        ),
    )
    validated = PortfolioQuestionResponse(
        status="answered", answer="고정 안내입니다.", citations=[], limitations=[]
    )

    def boom(system: str, user: str) -> Iterator[str]:  # must not be called
        raise AssertionError("compose must not run for a verbatim fallback")
        yield ""

    items = list(safe_answer_stream_items(validated, [r], "질문", streamer=boom, compose=False))
    assert isinstance(items[0], QaAgentMeta)
    deltas = [i.text for i in items if isinstance(i, QaAgentDelta)]
    assert deltas == ["고정 안내입니다."]
    assert isinstance(items[-1], QaAgentCompleted)


def test_safe_wrapper_terminates_after_partial_then_exception() -> None:
    r = _res(
        "암진단비 30,000,000원",
        ConsultationEvidence(
            id="c1", fact="암진단비 30,000,000원", coverage_name="암진단비", amount=30_000_000
        ),
    )
    validated = PortfolioQuestionResponse(
        status="answered", answer="암진단비는 30,000,000원이에요.", citations=[], limitations=[]
    )

    def partial(system: str, user: str) -> Iterator[str]:
        yield "안녕하세요. "  # 한 문장 방출
        raise RuntimeError("mid-stream")

    items = list(safe_answer_stream_items(validated, [r], "질문", streamer=partial))
    assert isinstance(items[-1], QaAgentCompleted)  # 반드시 종료
