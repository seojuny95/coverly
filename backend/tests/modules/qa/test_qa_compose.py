from collections.abc import Iterator

from app.modules.qa.agent.answer_spec import GroundedAnswerSpec
from app.modules.qa.agent.compose import (
    COMPOSE_SYSTEM,
    build_compose_prompt,
    compose_answer_stream,
)


def _spec() -> GroundedAnswerSpec:
    return GroundedAnswerSpec(
        mode="grounded",
        facts=("암진단비 가입 확인", "암수술비 가입 확인"),
        amounts={"amt1": "3,000만원", "amt2": "500만원"},
        grounding_sources=("암진단비 30,000,000원",),
        citations=[],
        limitations=[],
        claim_channels=None,
    )


def _situational_spec() -> GroundedAnswerSpec:
    return GroundedAnswerSpec(
        mode="grounded",
        facts=("암진단비 가입 확인", "암수술비 가입 확인"),
        amounts={"amt1": "3,000만원", "amt2": "500만원"},
        grounding_sources=("암진단비 30,000,000원",),
        citations=[],
        limitations=[],
        claim_channels=None,
        situational=True,
    )


def test_situational_compose_prompt_adds_empathy_and_option_guidance() -> None:
    _, user = build_compose_prompt(_situational_spec(), "대장암에 걸렸는데 어떻게 해?")
    assert "공감" in user  # 짧은 공감 지시
    assert "되묻" in user  # 옵션 되묻기 지시
    assert "보유" in user  # 보유 보장에서만 옵션
    assert "약관" in user  # 실제 지급은 약관 지급사유로 확인
    assert "지급사유" in user


def test_non_situational_compose_prompt_omits_option_guidance() -> None:
    _, user = build_compose_prompt(_spec(), "암진단비 가입금액 알려줘")
    assert "되묻" not in user


def test_system_prompt_forbids_raw_numbers() -> None:
    # 숫자는 자리표시자로만 쓰라는 지시가 시스템 프롬프트에 있다
    assert "{{" in COMPOSE_SYSTEM
    assert "판매" in COMPOSE_SYSTEM or "권유" in COMPOSE_SYSTEM  # 판매금지 규칙


def test_user_prompt_lists_available_labels_and_facts() -> None:
    system, user = build_compose_prompt(_spec(), "대장암 관련 보장 알려줘")
    assert "amt1" in user and "amt2" in user  # 사용 가능한 라벨 노출
    assert "3,000만원" in user and "500만원" in user  # 라벨의 확정값도 노출(치환 참고용)
    assert "암진단비 가입 확인" in user  # 근거 사실 포함
    assert "대장암" in user  # 질문 포함


def test_stream_yields_streamer_tokens() -> None:
    def fake_streamer(system: str, user: str) -> Iterator[str]:
        assert "{{" in system
        yield from ["암진단비는 ", "{{amt1}}", "이 있어요."]

    out = list(compose_answer_stream(_spec(), "질문", streamer=fake_streamer))
    assert out == ["암진단비는 ", "{{amt1}}", "이 있어요."]


def test_prompt_is_pii_masked() -> None:
    _, user = build_compose_prompt(_spec(), "제 주민번호는 900101-1234567인데 암보장 알려줘")
    assert "900101-1234567" not in user  # PII 마스킹 적용
