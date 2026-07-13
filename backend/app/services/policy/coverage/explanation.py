"""Official-source assisted explanations for coverages whose 보장내용 is absent.

One batched structured-output call explains every cache-missed name; results
are cached in-process by 담보명 because a general explanation is independent of
any particular policy. Official RAG excerpts are passed as context so the LLM
uses standard-clause terms and limitations before falling back to broad
coverage-name meaning.

Never raises: on LLM failure the caller gets cache hits plus ok=False so the
upload degrades to 분석상태=부분 instead of breaking.
"""

from collections.abc import Callable
from functools import lru_cache

from pydantic import BaseModel, ValidationError

from app.services.llm import (
    JsonCompleter,
    compact_prompt_text,
    dump_prompt_json,
    structured_completer,
)
from app.services.rag.official.models import RetrievalHit
from app.services.rag.official.retrieval import retrieve

_SYSTEM = (
    "너는 사용자가 이미 가진 보험의 담보를 이해하도록 돕는 상담사다. "
    "제공된 공식자료 발췌문이 있으면 그 내용을 우선 근거로 삼고, "
    "발췌문이 담보를 직접 설명하지 않으면 일반적인 담보명 의미만 조심스럽게 설명하라. "
    "목록의 각 담보가 무엇을 대비하는지 전문용어 없이 쉬운 말과 "
    "친근한 존댓말(~해요체)로 1~2문장씩 설명하라. "
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
            "설명목록": [
                {
                    "담보명": "입력 담보명과 정확히 같은 값",
                    "해설": "사용자에게 보여줄 쉬운 설명",
                }
            ]
        },
    }
    return dump_prompt_json(payload)


def _retrieve_official_context(name: str) -> list[RetrievalHit]:
    query = f"{name} 뜻 지급사유 면책 감액 보상하지 않는 사항"
    return retrieve(query, final_k=2)
