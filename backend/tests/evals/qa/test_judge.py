from typing import Any

from pydantic import BaseModel

from app.integrations.openai.client import JsonCompleter
from evals.qa.judge import judge_turn


def test_judge_receives_tool_evidence_and_reference_facts() -> None:
    captured: dict[str, str] = {}

    def completer_factory(_schema: type[BaseModel]) -> JsonCompleter:
        def complete(system: str, user: str) -> dict[str, Any]:
            captured["system"] = system
            captured["user"] = user
            return {
                "evidence_grade__passed": True,
                "evidence_grade__reason": "도구 근거와 일치합니다.",
            }

        return complete

    verdicts = judge_turn(
        question="암 보장개시일은 언제야?",
        history_text="",
        answer="90일이 지난 다음 날이에요.",
        grounding_context="도구 결과: 계약일부터 90일이 지난 다음 날",
        reference_facts=["암 보장개시일은 계약일부터 90일이 지난 다음 날"],
        rubric_keys=["evidence_grade"],
        rubric_descriptions={"evidence_grade": "도구 근거와 일치하는가"},
        completer_factory=completer_factory,
    )

    assert verdicts["evidence_grade"].passed is True
    assert "도구 결과: 계약일부터 90일" in captured["user"]
    assert "평가셋 작성자가 확인한 기준 사실" in captured["user"]
