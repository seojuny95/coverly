"""Streaming (SSE) variant of portfolio Q&A."""

from collections.abc import Iterator

from app.schemas.portfolio import PolicyInput
from app.services.portfolio_qa import stream_portfolio_answer


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


def test_stream_deterministic_amount_answer_is_single_delta() -> None:
    events = list(stream_portfolio_answer("암진단비 가입금액은 얼마야?", _policies()))

    assert events[0]["type"] == "meta"
    text = "".join(str(e["text"]) for e in events if e["type"] == "delta")
    assert "30,000,000원" in text
    assert events[-1]["type"] == "end"


def test_stream_claim_howto_carries_clickable_channels_in_end() -> None:
    events = list(stream_portfolio_answer("실손 어떻게 청구해?", _policies()))

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


def test_stream_llm_answer_has_no_channels_when_not_claim_related() -> None:
    def fake_stream(_system: str, _user: str) -> Iterator[str]:
        yield "암진단비 담보가 확인돼요."

    events = list(stream_portfolio_answer("내 보장 강점은?", _policies(), stream=fake_stream))

    assert events[-1]["claim_channels"] is None


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
