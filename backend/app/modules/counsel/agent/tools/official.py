"""Agent SDK tool for stable, general insurance guidance (not user-specific)."""

from agents import RunContextWrapper, function_tool
from pydantic import BaseModel

from app.core.untrusted import strip_injection_markers_by_line
from app.modules.counsel.context import CounselContext
from app.rag.official.answer import answer_official_question


class OfficialGuidanceResult(BaseModel):
    matched: bool
    answer: str
    limitations: list[str]


@function_tool
def retrieve_official_guidance(
    wrapper: RunContextWrapper[CounselContext],
    query: str,
) -> OfficialGuidanceResult:
    """변하지 않는 보험 용어나 표준 제도 기준에 대한 일반 안내를 검색합니다.

    이 결과는 일반적인 공식 기준이며, 사용자가 실제로 가입한 보험의 조건과
    다를 수 있습니다. 이 도구로 답할 때는 항상 그 사실을 함께 안내하고,
    사용자의 실제 계약 조건인 것처럼 단정하지 마세요.

    Args:
        query: 검색할 보험 용어나 제도에 대한 완전한 질문입니다.
    """

    answerer = wrapper.context.official_answer or answer_official_question
    result = answerer(query)
    if result.status != "answered":
        return OfficialGuidanceResult(matched=False, answer="", limitations=[])
    return OfficialGuidanceResult(
        matched=True,
        answer=strip_injection_markers_by_line(result.answer),
        limitations=list(result.limitations),
    )
