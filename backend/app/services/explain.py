"""General explanations for coverages whose 보장내용 is absent (Phase 1, interim).

One batched structured-output call explains every cache-missed name; results
are cached in-process by 담보명 because a general explanation is independent of
any particular policy. Phase 2 replaces these with 표준약관-grounded
explanations — until then the frontend labels them honestly as general.

Never raises: on LLM failure the caller gets cache hits plus ok=False so the
upload degrades to 분석상태=부분 instead of breaking.
"""

from functools import lru_cache

from pydantic import BaseModel, ValidationError

from app.services.llm import JsonCompleter, structured_completer

_SYSTEM = (
    "너는 표준적인 보험 담보를 일반적으로 설명하는 도우미다. "
    "목록의 각 담보가 일반적으로 무엇을 보장하는지 전문용어 없이 쉬운 말과 "
    "친근한 존댓말(~해요체)로 1~2문장씩 설명하라. "
    "금액·정확한 면책기간·감액률은 단정하지 말고 '보통', '상품마다 다를 수 있어요'처럼 표현하라. "
    "지어내지 말고 일반적으로 알려진 내용만 써라. "
    "일반적으로 알려진 내용이 없는 담보는 결과에서 제외하라."
)


class _Explanation(BaseModel):
    담보명: str
    해설: str


class _ExplanationBatch(BaseModel):
    설명목록: list[_Explanation]


_CACHE: dict[str, str] = {}


@lru_cache
def _default_completer() -> JsonCompleter:
    return structured_completer(_ExplanationBatch)


def explain_coverages(
    names: list[str], complete: JsonCompleter | None = None
) -> tuple[dict[str, str], bool]:
    """(담보명 -> 해설, ok): cache-first, one batch LLM call for the misses."""
    unique = list(dict.fromkeys(name.strip() for name in names if name.strip()))
    explanations = {name: _CACHE[name] for name in unique if name in _CACHE}
    missing = [name for name in unique if name not in _CACHE]
    if not missing:
        return explanations, True

    completer = complete or _default_completer()
    try:
        payload = completer(_SYSTEM, "\n".join(f"- {name}" for name in missing))
    except Exception:
        return explanations, False

    rows = payload.get("설명목록", [])
    if not isinstance(rows, list):
        return explanations, True
    for row in rows:
        try:
            parsed = _Explanation.model_validate(row)
        except ValidationError:
            continue
        name, text = parsed.담보명.strip(), parsed.해설.strip()
        if name in missing and text:
            _CACHE[name] = text
            explanations[name] = text
    return explanations, True
