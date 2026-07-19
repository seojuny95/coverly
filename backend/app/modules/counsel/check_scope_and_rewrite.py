"""Resolve context-dependent phrasing and classify domain scope in one LLM call."""

from pydantic import BaseModel

from app.integrations.openai.client import JsonCompleter
from app.modules.counsel.schemas import CounselMessage

_INSTRUCTIONS = """이전 대화와 현재 질문을 보고 두 가지를 판단하세요.

1. rewritten_question: 질문을 그 자체로 이해 가능한 독립된 질문으로 다시 쓰세요.
   - 대명사, 생략된 주어·목적어만 이전 대화 내용으로 채우세요.
   - 없는 사실이나 의도를 새로 지어내지 마세요.
   - 이전 대화가 없거나 무관하면 원문을 그대로 반환하세요.

2. in_scope: 재작성한 질문이 다음 중 하나에 해당하면 true입니다.
   - 사용자가 가입한 보험, 증권, 담보, 가입금액, 약관, 청구처럼 본인의 보험 정보에 관한 질문
     (이런 개인 정보 질문이 Coverly가 답하는 핵심 범위입니다)
   - 보험 제도나 용어에 관한 일반적인 질문
   - Coverly의 기능, 답변 범위, 개인정보 처리 방식에 관한 질문
   그 외의 질문(날씨, 잡담, 보험과 무관한 다른 주제 등)은 in_scope=false입니다.

보험 사실을 답하거나 추측하지 말고 판단 결과만 반환하세요."""


class ScopeAndRewriteResult(BaseModel):
    rewritten_question: str
    in_scope: bool
    reason: str


def check_scope_and_rewrite(
    question: str,
    history: list[CounselMessage],
    *,
    complete: JsonCompleter,
) -> ScopeAndRewriteResult:
    history_text = (
        "\n".join(f"{item.role}: {item.content}" for item in history)
        if history
        else "(이전 대화 없음)"
    )
    user = f"이전 대화:\n{history_text}\n\n질문: {question}"

    raw = complete(_INSTRUCTIONS, user)
    return ScopeAndRewriteResult.model_validate(raw)
