"""Explanations for coverages whose 보장내용 is absent.

The upload path uses `explain_coverages_fast`: deterministic, local, and
dependency-free. The slower `explain_coverages` remains available for call sites
that explicitly want official-source assisted LLM explanations.

Never raises: on LLM failure the caller gets cache hits plus ok=False so the
upload degrades to 분석상태=부분 instead of breaking.
"""

import re
from collections.abc import Callable
from functools import lru_cache

from pydantic import BaseModel, ValidationError

from app.integrations.openai import (
    JsonCompleter,
    compact_prompt_text,
    dump_prompt_json,
    structured_completer,
)
from app.modules.coverage.purpose import coverage_purpose
from app.modules.coverage.taxonomy import classify_coverage
from app.rag.official.models import RetrievalHit
from app.rag.official.retrieval import retrieve

_SYSTEM = (
    "너는 사용자가 이미 가진 보험의 담보를 이해하도록 돕는 상담사다. "
    "제공된 공식자료 발췌문이 있으면 그 내용을 우선 근거로 삼고, "
    "발췌문이 담보를 직접 설명하지 않으면 일반적인 담보명 의미만 조심스럽게 설명하라. "
    "목록의 각 담보가 어떤 상황에 대비하는지 전문용어 없이 쉬운 말과 "
    "친근한 존댓말(~해요체)로 1~2문장씩 설명하라. "
    "한 문장으로 충분하면 한 문장만 써라. "
    "가능하면 '어떤 상황에서', '어떻게 도움이 되는지', '왜 필요한지'가 자연스럽게 보이게 설명하라. "
    "예를 들어 사고, 진단, 수술, 고장처럼 사용자가 떠올릴 수 있는 상황을 먼저 말하고, "
    "치료비 부담을 덜거나 수리비를 보태거나 빠른 도움을 받을 수 있다는 식으로 "
    "도움의 방식이 드러나게 설명하라. "
    "다만 문장을 늘리기 위해 같은 뜻을 반복하지 마라. "
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


def explain_coverages_fast(names: list[str]) -> tuple[dict[str, str], bool]:
    """Local 담보명-based explanations for the upload path.

    These are general display helpers, not policy-condition summaries. The
    policy's own 보장내용 always stays authoritative when present; this only
    fills a user-friendly explanation when the PDF table has name + amount but
    no wording.
    """
    explanations: dict[str, str] = {}
    for name in dict.fromkeys(item.strip() for item in names if item.strip()):
        explanations[name] = _local_explanation(name)
    return explanations, True


def _local_explanation(name: str) -> str:
    normalized = re.sub(r"\s+", "", name)

    category = classify_coverage(normalized)
    if category:
        purpose = coverage_purpose(category)
        if purpose:
            return purpose

    for keyword, explanation in _LOCAL_EXPLANATION_RULES:
        if keyword in normalized:
            return explanation

    return (
        "담보명만으로는 세부 조건을 단정하기 어려워요. "
        "가입금액과 약관의 지급 조건을 함께 확인하는 항목이에요."
    )


_LOCAL_EXPLANATION_RULES: tuple[tuple[str, str], ...] = (
    (
        "대인배상",
        "자동차 사고로 다른 사람이 다치거나 사망한 상황을 살펴볼 때 기준이 되는 항목이에요.",
    ),
    (
        "대물배상",
        "자동차 사고로 다른 사람의 차량이나 재산에 손해가 생긴 상황을 살펴보는 항목이에요.",
    ),
    (
        "자동차상해",
        "자동차 사고로 운전자나 탑승자가 다친 상황에서 치료와 회복 부담을 점검하는 항목이에요.",
    ),
    (
        "무보험차상해",
        "보험 가입이 충분하지 않은 차량과의 사고처럼 보상 경로가 복잡할 때 보는 항목이에요.",
    ),
    ("자기차량손해", "내 차량에 생긴 손해와 수리 부담을 확인할 때 보는 항목이에요."),
    (
        "긴급출동",
        "차량 고장이나 운행 중 긴급 상황에서 받을 수 있는 지원 범위를 확인하는 항목이에요.",
    ),
    ("벌금", "사고나 법적 책임으로 벌금 부담이 생길 수 있는 상황을 살펴보는 항목이에요."),
    ("배상", "다른 사람에게 손해를 끼쳐 책임이 생길 수 있는 상황을 확인하는 항목이에요."),
    ("화재", "화재로 재산 손해나 비용 부담이 생기는 상황을 살펴보는 항목이에요."),
    ("고장수리", "가전이나 생활 기기 고장으로 수리비가 생길 때 확인하는 항목이에요."),
    ("치료비", "치료 과정에서 생기는 비용 부담을 점검하는 항목이에요."),
    ("진단비", "질병이나 사고가 진단된 뒤 필요한 목돈과 생활비 공백을 살펴보는 항목이에요."),
)


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
