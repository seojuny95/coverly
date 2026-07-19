from app.modules.qa.agent.contracts import QaInputDecision
from app.modules.qa.agent.prompt import agent_instructions, build_agent_input
from app.modules.qa.context import build_qa_context


def test_agent_input_allows_multi_result_synthesis() -> None:
    context = build_qa_context("두 증권 암진단비 각각 얼마야?", [], None, [])
    prompt = build_agent_input(context)
    assert "하나를 선택" not in prompt
    assert "여러 도구" in prompt  # 종합 지시 존재


def _situational_decision(is_situational: bool) -> QaInputDecision:
    return QaInputDecision(
        scope="insurance",
        should_block=False,
        requires_fresh_official_source=False,
        is_situational=is_situational,
        insurance_request="대장암 진단을 받았는데 관련 보장을 봐줘",
        out_of_scope_request=None,
        reason="상황형 질문",
    )


def test_agent_instructions_add_situational_routing() -> None:
    instructions = agent_instructions(_situational_decision(True))
    assert "inspect_portfolio" in instructions
    assert "되묻" in instructions  # 옵션 되묻기 지시
    assert "보유" in instructions  # 보유 보장 한정


def test_agent_instructions_omit_situational_routing_when_not_situational() -> None:
    instructions = agent_instructions(_situational_decision(False))
    # 상황형 전용 되묻기 라우트 컨텍스트는 붙지 않는다
    assert "고르도록 되묻는" not in instructions
