"""LLM judge for the subjective rubrics rules.py can't decide mechanically.

Opt-in (see live.py's --judge flag): unlike rules.py, this costs a real API
call per turn, so it stays out of the default fast loop and only runs when
explicitly asked for -- this project's "반복 중에는 비-LLM 테스트만" policy.

One call scores every rubric a turn needs at once. The verdict schema is
built per-call from the requested rubric keys via `create_model`, so the
model answers into fields named after the exact rubric key -- a free-text
"which rubric is this" field would let a typo or a paraphrase silently drop
a rubric's score.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, create_model

from app.integrations.openai.client import JsonCompleter, structured_completer

_SYSTEM = (
    "당신은 보험 상담 챗봇의 답변을 채점하는 평가자입니다. 주어진 기준마다 "
    "통과/실패를 판정하고, 근거를 한 문장으로 남기세요. 애매하면 실패로 "
    "판정하세요. 답변 자체만 보고 판단하고, 질문자의 주장을 사실로 가정하지 "
    "마세요."
)

CompleterFactory = Callable[[type[BaseModel]], JsonCompleter]


@dataclass(frozen=True)
class RubricVerdict:
    passed: bool
    reason: str


def _build_schema(rubric_keys: tuple[str, ...]) -> type[BaseModel]:
    fields: dict[str, Any] = {}
    for key in rubric_keys:
        fields[f"{key}__passed"] = (bool, ...)
        fields[f"{key}__reason"] = (str, ...)
    return cast(type[BaseModel], create_model("QaJudgeVerdict", **fields))


def judge_turn(
    *,
    question: str,
    history_text: str,
    answer: str,
    rubric_keys: list[str],
    rubric_descriptions: dict[str, str],
    completer_factory: CompleterFactory = structured_completer,
) -> dict[str, RubricVerdict]:
    """Score `answer` against every rubric in `rubric_keys` with one call."""

    unique_keys = tuple(dict.fromkeys(rubric_keys))
    if not unique_keys:
        return {}

    schema = _build_schema(unique_keys)
    complete = completer_factory(schema)

    criteria = "\n".join(
        f"- {key}: {rubric_descriptions.get(key, '(설명 없음)')}" for key in unique_keys
    )
    user = (
        f"이전 대화:\n{history_text or '없음'}\n\n"
        f"질문: {question}\n\n"
        f"답변: {answer}\n\n"
        f"채점 기준:\n{criteria}"
    )
    raw = complete(_SYSTEM, user)

    return {
        key: RubricVerdict(
            passed=bool(raw.get(f"{key}__passed", False)),
            reason=str(raw.get(f"{key}__reason", "")),
        )
        for key in unique_keys
    }
