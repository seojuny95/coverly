from app.modules.qa.agent.prompt import build_agent_input
from app.modules.qa.context import build_qa_context


def test_agent_input_allows_multi_result_synthesis() -> None:
    context = build_qa_context("두 증권 암진단비 각각 얼마야?", [], None, [])
    prompt = build_agent_input(context)
    assert "하나를 선택" not in prompt
    assert "여러 도구" in prompt  # 종합 지시 존재
