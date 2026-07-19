"""LLM explanations for coverages whose 보장내용 is absent.

Never raises: on LLM failure the caller gets cache hits plus ok=False so the
upload degrades to 분석상태=부분 instead of breaking.
"""

from collections.abc import Callable
from functools import lru_cache

from pydantic import BaseModel, ValidationError

from app.integrations.openai import (
    JsonCompleter,
    compact_prompt_text,
    dump_prompt_json,
    structured_completer,
)
from app.rag.official.models import RetrievalHit
from app.rag.official.retrieval import retrieve

_SYSTEM = (
    "너는 사용자가 이미 가진 보험의 담보를 이해하도록 돕는 상담사다. "
    "제공된 공식자료 발췌문이 있으면 그 내용을 우선 근거로 삼고, "
    "발췌문이 담보를 직접 설명하지 않으면 일반적인 담보명 의미만 조심스럽게 설명하라. "
    "목록의 각 담보를 전문용어 없이 쉬운 말과 친근한 존댓말(~해요체)로 설명하라. "
    "해설은 1~2문장, 90자 안팎으로 쓴다. "
    "첫 문장에는 사용자가 떠올릴 수 있는 상황(사고, 진단, 수술, 입원, 고장, 법적 책임 등)을 넣고, "
    "둘째 문장이 필요하면 무엇을 확인하면 좋은지"
    "(치료비, 수리비, 책임 범위, 서비스 범위, 지급 조건 등)를 덧붙인다. "
    "'살펴보는 항목이에요', '확인하는 항목이에요'만으로 끝내지 말고, "
    "그 상황에서 왜 보는지까지 쉽게 풀어라. "
    "문장 패턴을 기계적으로 반복하지 말고, 담보마다 자연스럽게 풀어 써라. "
    "'보험이에요', '도움을 주는 보험이에요', '보상해주는 내용이에요' 같은 "
    "뻔한 끝맺음을 반복하지 마라. "
    "'추가적인', '일반적인', '비슷한'처럼 뜻이 흐린 표현은 피하고, "
    "대신 사용자가 어떤 상황을 떠올리면 되는지 짧고 분명하게 설명하라. "
    "특약은 담보와 똑같이 설명하지 말고, 서비스나 추가 지원처럼 역할에 맞게 설명하라. "
    "보험금 지급, 면책, 감액, 금액, 정확한 조건은 단정하지 말고 "
    "확인되지 않은 조건은 설명에 포함하지 마라. "
    "약관 확인이 필요하다는 안내나 설명의 출처·한계는 덧붙이지 마라. "
    "특정 보험사·상품 조건을 지어내지 마라. 설명할 수 없는 담보는 결과에서 제외하라."
)

_MAX_EXCERPT_CHARS = 700


class _Explanation(BaseModel):
    담보명: str
    해설: str


class _ExplanationBatch(BaseModel):
    설명목록: list[_Explanation]


_CACHE: dict[str, str] = {}
CoverageContextRetriever = Callable[[str], list[RetrievalHit]]


@lru_cache
def _default_completer() -> JsonCompleter:
    return structured_completer(_ExplanationBatch)


def explain_coverages(
    names: list[str],
    complete: JsonCompleter | None = None,
    retrieve_context: CoverageContextRetriever | None = None,
) -> tuple[dict[str, str], bool]:
    """(담보명 -> 해설, ok): cache-first, one batch LLM call for the misses."""
    unique = list(dict.fromkeys(name.strip() for name in names if name.strip()))
    explanations = {name: _CACHE[name] for name in unique if name in _CACHE}
    missing = [name for name in unique if name not in _CACHE]
    if not missing:
        return explanations, True

    completer = complete or _default_completer()
    try:
        payload = completer(_SYSTEM, _user_prompt(missing, retrieve_context))
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


def _user_prompt(
    names: list[str],
    retrieve_context: CoverageContextRetriever | None,
) -> str:
    retriever = retrieve_context or _retrieve_official_context
    payload = {
        "coverages": [
            {
                "name": name,
                "official_excerpts": [
                    {
                        "id": hit.chunk.id,
                        "source_title": hit.chunk.source_title,
                        "citation_label": hit.chunk.citation_label,
                        "text": compact_prompt_text(hit.chunk.text, _MAX_EXCERPT_CHARS),
                    }
                    for hit in retriever(name)
                ],
            }
            for name in names
        ],
        "output": {
            "style": {
                "length": "1~2문장, 90자 안팎",
                "must_include": (
                    "담보명에서 알 수 있는 생활 상황과 사용자가 확인할 비용·책임·서비스 범위"
                ),
                "avoid": "단순히 '살펴보는 항목', '확인하는 항목'이라고만 끝내는 설명",
            },
            "설명목록": [
                {
                    "담보명": "입력 담보명과 정확히 같은 값",
                    "해설": "사용자에게 보여줄 쉽고 구체적인 짧은 설명",
                }
            ],
        },
    }
    return dump_prompt_json(payload)


def _retrieve_official_context(name: str) -> list[RetrievalHit]:
    query = f"{name} 뜻 보장내용 지급사유 보상 범위 면책 감액 보상하지 않는 사항"
    return retrieve(query, final_k=3)
