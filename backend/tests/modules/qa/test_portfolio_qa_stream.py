"""Streaming (SSE) variant of portfolio Q&A."""

from collections.abc import Iterator

from pytest import MonkeyPatch

from app.modules.portfolio.schemas import PolicyInput
from app.modules.qa.schemas import ConversationMessage, PortfolioQuestionResponse
from app.modules.qa.service import stream_portfolio_answer
from app.rag.official.answer import RagAnswer, RagCitation


def _policies() -> list[PolicyInput]:
    return [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "삼성화재", "상품명": "건강보험", "보험분류": "질병"},
                "보장목록": [
                    {"담보명": "암진단비", "가입금액": "3,000만원", "지급유형": "정액"},
                    {"담보명": "실손의료비", "가입금액": "5,000만원", "지급유형": "실손"},
                ],
            }
        )
    ]


def _official_answer(_: str) -> RagAnswer:
    return RagAnswer(
        status="answered",
        mode="claim_check",
        answer=(
            "표준약관 기준으로는 지급사유와 면책 사유를 확인해야 해요.\n\n"
            "최종 지급 여부는 가입한 상품 약관과 보험사 심사로 확정돼요."
        ),
        citations=(
            RagCitation(
                chunk_id="official-claim-1",
                source_id="standard_terms_annex_15_2026_06_30",
                source_title="보험업감독업무시행세칙 별표15 표준약관",
                source_category="standard_clause",
                publisher="금융감독원",
                citation_label="표준약관 제3조(보험금의 지급사유)",
                page_start=12,
                page_end=12,
                version_label="시행일 2026-06-30",
                source_url="https://www.law.go.kr/LSW/flDownload.do?flSeq=166365465",
            ),
        ),
        limitations=("표준약관 기준의 일반 확인 안내입니다.",),
    )


def test_stream_routes_official_rag_as_multiple_deltas() -> None:
    events = list(
        stream_portfolio_answer(
            "암 진단비 받을 수 있는지 확인 기준 알려줘",
            _policies(),
            official_answer=_official_answer,
        )
    )

    assert events[0]["type"] == "meta"
    deltas = [str(event["text"]) for event in events if event["type"] == "delta"]
    text = "".join(deltas)
    assert len(deltas) > 1
    assert "지급사유" in text
    end = events[-1]
    assert end["type"] == "end"
    citations = end["citations"]
    assert isinstance(citations, list)
    assert citations[0]["source_id"] == "standard_terms_annex_15_2026_06_30"


def test_stream_llm_answer_yields_deltas_then_end_with_citations() -> None:
    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "암진단비를"
        yield " 확인했어요."

    events = list(stream_portfolio_answer("내 보장 어떻게 볼까?", _policies(), stream=fake_stream))

    assert events[0]["type"] == "meta"
    assert events[0]["generation"] == "llm"
    assert events[-1]["type"] == "end"
    text = "".join(str(e["text"]) for e in events if e["type"] == "delta")
    assert text == "암진단비를 확인했어요."
    citations = events[-1]["citations"]
    assert isinstance(citations, list)
    assert any(c.get("coverage_name") == "암진단비" for c in citations)


def test_stream_deterministic_amount_answer_is_multiple_deltas() -> None:
    events = list(stream_portfolio_answer("암진단비 가입금액은 얼마야?", _policies()))

    assert events[0]["type"] == "meta"
    deltas = [str(e["text"]) for e in events if e["type"] == "delta"]
    text = "".join(deltas)
    assert len(deltas) > 1
    assert "**30,000,000원**" in text
    assert "30,000,000원" in text
    assert events[-1]["type"] == "end"
    suggestions = events[-1]["suggestions"]
    assert isinstance(suggestions, list)
    assert suggestions
    assert all(suggestion.endswith("?") for suggestion in suggestions)
    assert not any("해 주세요" in suggestion for suggestion in suggestions)


def test_stream_uses_agent_first_for_deterministic_question() -> None:
    class CountingAgent:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, _context: object) -> PortfolioQuestionResponse:
            self.calls += 1
            return PortfolioQuestionResponse(
                status="answered",
                answer="Agent가 가입 목록 도구로 확인했어요.",
                citations=[],
                limitations=[],
                suggestions=[],
                generation="llm",
            )

    agent = CountingAgent()
    events = list(
        stream_portfolio_answer(
            "가입한 보험은 몇 개야?",
            _policies(),
            agent_runner=agent,
        )
    )

    text = "".join(str(event["text"]) for event in events if event["type"] == "delta")
    assert agent.calls == 1
    assert "Agent가 가입 목록 도구로 확인했어요." in text


def test_stream_agent_failure_does_not_call_legacy_consultation_model(
    monkeypatch: MonkeyPatch,
) -> None:
    class FailedAgent:
        def run(self, _context: object) -> PortfolioQuestionResponse:
            raise RuntimeError("offline")

    def forbidden_legacy_stream(*_args: object, **_kwargs: object) -> Iterator[object]:
        raise AssertionError("agent failure must not trigger a second model call")
        yield {}  # pragma: no cover

    monkeypatch.setattr(
        "app.modules.qa.service.stream_consultation_answer",
        forbidden_legacy_stream,
    )

    events = list(
        stream_portfolio_answer(
            "내 보험 강점을 설명해줘",
            _policies(),
            agent_runner=FailedAgent(),
        )
    )

    assert events[0]["generation"] == "fallback"
    assert events[-1]["type"] == "end"


def test_stream_claim_howto_carries_clickable_channels_in_end() -> None:
    events = list(stream_portfolio_answer("실손의료보험 어떻게 청구해?", _policies()))

    end = events[-1]
    assert end["type"] == "end"
    assert end["claim_channels"] is not None


def test_stream_llm_answer_attaches_claim_channels_when_claim_related() -> None:
    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "암진단비는 진단서를 내고 보험금을 청구하시면 돼요."

    events = list(stream_portfolio_answer("보험금 어떻게 받아?", _policies(), stream=fake_stream))

    end = events[-1]
    assert end["type"] == "end"
    channels = end["claim_channels"]
    assert isinstance(channels, dict)
    assert any(insurer["name"] == "삼성화재" for insurer in channels["insurers"])


def test_stream_channels_limited_to_the_cited_coverage_insurer() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "삼성화재", "상품명": "암보험", "보험분류": "질병"},
                "보장목록": [{"담보명": "암진단비", "가입금액": "3,000만원", "지급유형": "정액"}],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "p2",
                "기본정보": {"보험사": "현대해상", "상품명": "상해보험", "보험분류": "상해"},
                "보장목록": [{"담보명": "골절진단비", "가입금액": "100만원", "지급유형": "정액"}],
            }
        ),
    ]

    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "암진단비는 진단서를 내고 보험금을 청구하시면 돼요."

    events = list(stream_portfolio_answer("암 보험금 어떻게 받아?", policies, stream=fake_stream))

    channels = events[-1]["claim_channels"]
    assert isinstance(channels, dict)
    names = [insurer["name"] for insurer in channels["insurers"]]
    assert "삼성화재" in names
    assert "현대해상" not in names


def test_stream_channels_resolve_coverage_with_paren_suffix() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "흥국화재", "상품명": "맘편한보험", "보험분류": "질병"},
                "보장목록": [
                    {"담보명": "암진단비(유사암제외)", "가입금액": "6,000만원", "지급유형": "정액"}
                ],
            }
        )
    ]

    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "암 진단비가 6,000만 원으로 확인돼요. 진단서를 준비해 보험금을 청구하세요."

    events = list(stream_portfolio_answer("대장암 걸렸어 어떻게 해?", policies, stream=fake_stream))

    end = events[-1]
    channels = end["claim_channels"]
    assert isinstance(channels, dict)
    assert any(insurer["name"] == "흥국화재" for insurer in channels["insurers"])
    citations = end["citations"]
    assert isinstance(citations, list)
    assert any(c.get("coverage_name") == "암진단비(유사암제외)" for c in citations)


def test_stream_medical_indemnity_channel_survives_paren_suffix() -> None:
    """A 실손 coverage whose name carries a "(질병)"-style suffix must still route to
    the medical-indemnity (실손24) claim channel, not lose it to name normalization."""

    policies = [
        PolicyInput.model_validate(
            {
                "id": "p1",
                "기본정보": {"보험사": "삼성화재", "상품명": "건강보험", "보험분류": "질병"},
                "보장목록": [
                    {"담보명": "실손의료비(질병)", "가입금액": "5,000만원", "지급유형": "실손"}
                ],
            }
        )
    ]

    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "실손의료비는 진료비 영수증을 내고 보험금을 청구하시면 돼요."

    events = list(stream_portfolio_answer("보험금 어떻게 받아?", policies, stream=fake_stream))

    channels = events[-1]["claim_channels"]
    assert isinstance(channels, dict)
    assert any(insurer["name"] == "삼성화재" for insurer in channels["insurers"])
    assert channels["medical_indemnity"] is not None
    assert channels["medical_indemnity"]["name"] == "실손24"


def test_stream_travel_medical_context_does_not_route_to_medical_indemnity() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "health",
                "기본정보": {
                    "보험사": "삼성화재",
                    "상품명": "건강보험",
                    "보험분류": "질병",
                },
                "보장목록": [{"담보명": "국내질병입원의료비", "지급유형": "실손"}],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "travel",
                "기본정보": {
                    "보험사": "현대해상",
                    "상품명": "해외여행자보험",
                    "보험분류": "여행자보험",
                    "상품태그": ["여행자보험"],
                },
                "보장목록": [{"담보명": "국내질병입원의료비", "지급유형": "실손"}],
            }
        ),
    ]

    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "해외여행자보험의 국내질병입원의료비는 현대해상에서 청구하세요."

    events = list(
        stream_portfolio_answer(
            "여행 중 병원비는 어떻게 처리해?",
            policies,
            stream=fake_stream,
        )
    )

    channels = events[-1]["claim_channels"]
    assert isinstance(channels, dict)
    assert [insurer["name"] for insurer in channels["insurers"]] == ["현대해상"]
    assert channels["medical_indemnity"] is None


def test_stream_ambiguous_medical_name_does_not_assume_medical_indemnity() -> None:
    policies = [
        PolicyInput.model_validate(
            {
                "id": "health",
                "기본정보": {
                    "보험사": "삼성화재",
                    "상품명": "건강보험",
                    "보험분류": "질병",
                },
                "보장목록": [{"담보명": "국내질병입원의료비", "지급유형": "실손"}],
            }
        ),
        PolicyInput.model_validate(
            {
                "id": "travel",
                "기본정보": {
                    "보험사": "현대해상",
                    "상품명": "해외여행자보험",
                    "보험분류": "여행자보험",
                    "상품태그": ["여행자보험"],
                },
                "보장목록": [{"담보명": "국내질병입원의료비", "지급유형": "실손"}],
            }
        ),
    ]

    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "국내질병입원의료비는 가입한 보험사에서 청구하세요."

    events = list(
        stream_portfolio_answer(
            "국내질병입원의료비는 어디에 청구해?",
            policies,
            stream=fake_stream,
        )
    )

    channels = events[-1]["claim_channels"]
    assert isinstance(channels, dict)
    assert {insurer["name"] for insurer in channels["insurers"]} == {"삼성화재", "현대해상"}
    assert channels["medical_indemnity"] is None


def _auto_policy(insurer: str) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": "auto1",
            "기본정보": {"보험사": insurer, "상품명": "다이렉트자동차보험", "보험분류": "자동차"},
            "보장목록": [
                {"담보명": "대물배상", "지급유형": "실손"},
                {"담보명": "자기차량손해", "지급유형": "실손"},
            ],
        }
    )


def test_stream_gives_auto_insurer_channel_for_accident_answer() -> None:
    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "자동차 사고가 나셨군요. 대물배상으로 청구하시면 돼요."

    events = list(
        stream_portfolio_answer(
            "사고 났어 어떻게 청구해?", [_auto_policy("삼성화재")], stream=fake_stream
        )
    )

    channels = events[-1]["claim_channels"]
    assert isinstance(channels, dict)
    assert any(insurer["name"] == "삼성화재" for insurer in channels["insurers"])


def test_stream_answers_auto_only_portfolio_instead_of_no_data() -> None:
    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "가입하신 자동차보험으로 사고를 접수하실 수 있어요."

    events = list(
        stream_portfolio_answer(
            "나 자동차 사고 났어 어떻게 해?", [_auto_policy("삼성화재")], stream=fake_stream
        )
    )

    assert events[0]["status"] != "no_data"
    text = "".join(str(e["text"]) for e in events if e["type"] == "delta")
    assert "자동차보험" in text


def test_stream_llm_answer_has_no_channels_when_not_claim_related() -> None:
    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "암진단비 담보가 확인돼요."

    events = list(stream_portfolio_answer("내 보장 강점은?", _policies(), stream=fake_stream))

    assert events[-1]["claim_channels"] is None


def test_stream_places_current_question_after_prior_conversation() -> None:
    captured: dict[str, str] = {}

    def fake_stream(_system: str, user: str) -> Iterator[str]:
        captured["user"] = user
        yield "네, 확인했어요."

    list(
        stream_portfolio_answer(
            "지금은 뭘 봐야 해?",
            _policies(),
            history=[
                ConversationMessage(role="user", content="암진단비 알려줘"),
                ConversationMessage(role="assistant", content="암진단비는 3천만원이에요"),
            ],
            stream=fake_stream,
        )
    )

    user = captured["user"]
    assert "지금은 뭘 봐야 해?" in user
    assert user.index("암진단비 알려줘") < user.index("지금은 뭘 봐야 해?")


def test_stream_clarifying_question_drops_grounding_furniture() -> None:
    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "CLARIFY\n"
        yield "어떤 사고였는지 알려주시겠어요?"

    events = list(stream_portfolio_answer("사고났어 어떻게 해?", _policies(), stream=fake_stream))

    text = "".join(str(e["text"]) for e in events if e["type"] == "delta")
    assert text == "어떤 사고였는지 알려주시겠어요?"
    assert "CLARIFY" not in text
    end = events[-1]
    assert end["status"] == "clarify"
    assert end["citations"] == []
    assert end["limitations"] == []
    assert end["claim_channels"] is None


def test_stream_clarify_strips_token_written_on_the_same_line() -> None:
    for prefix in ("CLARIFY ", "CLARIFY: ", "clarify\n"):

        def fake_stream(_s: str, _u: str, prefix: str = prefix) -> Iterator[str]:
            yield f"{prefix}어떤 사고인지 알려주시겠어요?"

        events = list(
            stream_portfolio_answer("사고 났어 어떻게 해?", _policies(), stream=fake_stream)
        )

        text = "".join(str(e["text"]) for e in events if e["type"] == "delta")
        assert text == "어떤 사고인지 알려주시겠어요?", prefix
        assert "CLARIFY" not in text.upper()
        assert events[-1]["status"] == "clarify"


def test_stream_empty_clarify_falls_back_with_single_meta() -> None:
    def fake_stream(_s: str, _u: str) -> Iterator[str]:
        yield "CLARIFY\n"

    events = list(stream_portfolio_answer("사고 났어 어떻게 해?", _policies(), stream=fake_stream))

    metas = [event for event in events if event["type"] == "meta"]
    assert len(metas) == 1
    assert events[-1]["type"] == "end"
    assert events[0]["generation"] == "fallback"


def test_stream_falls_back_when_streamer_errors_before_any_token() -> None:
    def broken(_system: str, _user: str) -> Iterator[str]:
        raise RuntimeError("offline")
        yield ""  # pragma: no cover

    events = list(stream_portfolio_answer("내 보장 어떻게 볼까?", _policies(), stream=broken))

    assert events[0]["type"] == "meta"
    assert events[0]["generation"] == "fallback"
    assert events[-1]["type"] == "end"
    text = "".join(str(e["text"]) for e in events if e["type"] == "delta")
    assert text


def test_stream_resolves_contextual_question_before_fast_answer() -> None:
    events = list(
        stream_portfolio_answer(
            "그건 얼마야?",
            _policies(),
            history=[ConversationMessage(role="assistant", content="암진단비를 확인했어요.")],
            plan=lambda _system, _user: {
                "questions": [
                    {
                        "original": "그건 얼마야?",
                        "resolved": "암진단비 가입금액은 얼마야?",
                        "scope": "insurance",
                    }
                ],
                "clarification": None,
            },
        )
    )

    text = "".join(str(event.get("text", "")) for event in events)
    assert "30,000,000원" in text


def test_stream_answers_insurance_part_and_limits_out_of_scope_part() -> None:
    events = list(
        stream_portfolio_answer(
            "암진단비 알려주고 오늘 날씨도 알려줘",
            _policies(),
            plan=lambda _system, _user: {
                "questions": [
                    {
                        "original": "암진단비 알려주고",
                        "resolved": "암진단비 가입금액은 얼마야?",
                        "scope": "insurance",
                    },
                    {
                        "original": "오늘 날씨도 알려줘",
                        "resolved": "오늘 날씨는 어때?",
                        "scope": "out_of_scope",
                    },
                ],
                "clarification": None,
            },
        )
    )

    text = "".join(str(event.get("text", "")) for event in events)
    assert "30,000,000원" in text
    assert "**보험과 관련 없는 정보**는 답변하기 어려워요" in text
    assert events[-1]["status"] == "answered"
    suggestions = events[-1]["suggestions"]
    assert isinstance(suggestions, list)
    assert suggestions
    assert all(suggestion.endswith("?") for suggestion in suggestions)


def test_stream_clarifies_ambiguous_reference() -> None:
    events = list(
        stream_portfolio_answer(
            "그건 얼마야?",
            _policies(),
            plan=lambda _system, _user: {
                "questions": [
                    {
                        "original": "그건 얼마야?",
                        "resolved": "대상을 확인해야 하는 가입금액 질문",
                        "scope": "insurance",
                    }
                ],
                "clarification": "어떤 담보의 가입금액을 말씀하시는지 알려주세요.",
            },
        )
    )

    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "end"
    assert sum(event["type"] == "delta" for event in events) > 1
    assert events[0]["status"] == "clarify"
    assert (
        "".join(str(event["text"]) for event in events if event["type"] == "delta")
        == "어떤 담보의 가입금액을 말씀하시는지 알려주세요."
    )
    assert events[-1]["status"] == "clarify"
