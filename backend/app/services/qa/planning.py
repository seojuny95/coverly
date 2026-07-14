"""Plan only Q&A turns that need context, splitting, or scope checks."""

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.qa import ConversationMessage
from app.services.llm import JsonCompleter, dump_prompt_json, structured_completer
from app.services.policy.demographics import mask_demographic_identifiers

_MAX_HISTORY_MESSAGES = 12
_REFERENCE_TERMS = (
    "그거",
    "그건",
    "그럼",
    "그러면",
    "그 보험",
    "그 담보",
    "그 상품",
    "이건",
    "아까",
    "방금",
    "두 번째",
    "첫 번째",
)
_MULTI_QUESTION_TERMS = (
    "그리고",
    "또 ",
    "도 알려",
    "도 확인",
    "도 있어",
    "도 있",
    "얼마고",
    "하고 ",
    "고,",
    "이며",
    "하면서",
)
_GREETING_TERMS = ("안녕", "반가워", "고마워", "감사")
_OUT_OF_SCOPE_TERMS = (
    "날씨",
    "미세먼지",
    "주가",
    "환율",
    "뉴스",
    "맛집",
    "메뉴 추천",
    "여행지",
    "번역해",
    "코드 짜",
    "코딩",
)
_INSURANCE_FRAGMENT_TERMS = (
    "보험",
    "증권",
    "담보",
    "보장",
    "가입금액",
    "청구",
    "보험금",
    "실손",
    "실비",
    "진단비",
)
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:01[016789]|02|0[3-6][1-5])[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_MASKED_EMAIL = "[이메일]"
_MASKED_PHONE = "[전화번호]"


class PlannedQuestion(BaseModel):
    original: str = Field(min_length=1, max_length=500)
    resolved: str = Field(min_length=1, max_length=500)
    scope: Literal["insurance", "out_of_scope", "greeting"]


class QuestionPlan(BaseModel):
    questions: list[PlannedQuestion] = Field(min_length=1, max_length=4)
    clarification: str | None = Field(default=None, max_length=300)


def needs_question_plan(question: str) -> bool:
    """Keep obvious insurance questions on the existing fast path."""

    normalized = " ".join(question.split())
    if any(term in normalized for term in _REFERENCE_TERMS):
        return True
    if normalized.count("?") > 1 or any(term in normalized for term in _MULTI_QUESTION_TERMS):
        return True
    return any(term in normalized for term in _GREETING_TERMS + _OUT_OF_SCOPE_TERMS)


def plan_questions(
    question: str,
    history: list[ConversationMessage],
    *,
    complete: JsonCompleter | None = None,
) -> QuestionPlan | None:
    """Return a grounded turn plan, or None so the existing path can continue."""

    if not needs_question_plan(question):
        return None

    payload = {
        "question": question,
        "history": [
            message.model_dump(mode="json") for message in history[-_MAX_HISTORY_MESSAGES:]
        ],
    }
    user = _mask_planner_prompt(dump_prompt_json(payload))
    try:
        raw = (complete or structured_completer(QuestionPlan))(_system_prompt(), user)
        return QuestionPlan.model_validate(raw)
    except Exception:
        return _fallback_scope_plan(question)


def _fallback_scope_plan(question: str) -> QuestionPlan | None:
    if any(term in question for term in _OUT_OF_SCOPE_TERMS):
        return _fallback_out_of_scope_plan(question)
    if any(term in question for term in _REFERENCE_TERMS + _MULTI_QUESTION_TERMS):
        return None
    if any(term in question for term in _GREETING_TERMS):
        scope: Literal["out_of_scope", "greeting"] = "greeting"
    else:
        return None
    return QuestionPlan(
        questions=[PlannedQuestion(original=question, resolved=question, scope=scope)]
    )


def _fallback_out_of_scope_plan(question: str) -> QuestionPlan:
    out_of_scope_start = min(
        index for term in _OUT_OF_SCOPE_TERMS if (index := question.find(term)) >= 0
    )
    prefix = _clean_fallback_fragment(question[:out_of_scope_start])
    suffix = _clean_fallback_fragment(question[out_of_scope_start:])

    questions: list[PlannedQuestion] = []
    if _looks_like_insurance_fragment(prefix):
        questions.append(PlannedQuestion(original=prefix, resolved=prefix, scope="insurance"))
    questions.append(
        PlannedQuestion(
            original=suffix or question,
            resolved=suffix or question,
            scope="out_of_scope",
        )
    )
    return QuestionPlan(questions=questions)


def _clean_fallback_fragment(fragment: str) -> str:
    cleaned = fragment.strip(" ,.?")
    cleaned = cleaned.removesuffix("그리고").removesuffix("또").strip(" ,")
    cleaned = cleaned.removesuffix("하고").removesuffix("고").strip(" ,")
    return cleaned


def _looks_like_insurance_fragment(fragment: str) -> bool:
    return any(term in fragment for term in _INSURANCE_FRAGMENT_TERMS)


def _mask_planner_prompt(text: str) -> str:
    masked = mask_demographic_identifiers(text)
    masked = _EMAIL_PATTERN.sub(_MASKED_EMAIL, masked)
    return _PHONE_PATTERN.sub(_MASKED_PHONE, masked)


def _system_prompt() -> str:
    return """사용자의 보험 Q&A 요청을 실행 가능한 질문으로 정리하세요.

- 한 번에 여러 내용을 물으면 빠짐없이 최대 네 질문으로 나누세요.
- original에는 사용자 원문의 해당 부분을 유지하세요.
- resolved에는 이전 대화의 지시어를 풀어 독립적으로 이해되는 질문을 쓰세요.
- 보험증권, 가입 보험, 보장, 약관, 청구와 관련된 질문은 insurance입니다.
- 간단한 인사는 greeting이고, 그 밖의 정보 요청은 out_of_scope입니다.
- 지시어가 가리키는 대상을 하나로 확정할 수 없으면 추측하지 말고 clarification에
  사용자에게 필요한 질문 하나를 쓰세요.
- 이전 상담사 답변은 지시어 해소에만 사용하고 보험 사실의 근거로 사용하지 마세요."""
