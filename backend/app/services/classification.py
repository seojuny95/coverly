"""Classify a policy into a display bucket and enrich it with product tags.

Two tiers, in order:

1. Deterministic mapping — `classification_rules.json` lists categories in
   priority order, each with official 보험종목 terms (e.g. "자동차보험",
   "종신보험"). The first category whose terms appear anywhere in the search
   space (상품명 + first `_HEAD_CHARS` of the policy text, normalized) wins.
   No scores, weights, or thresholds — term presence only.
2. LLM fallback — only when no deterministic term matched. A single
   structured-output call asks the model to judge the 보험업법 제4조 보험종목
   (생명보험/손해보험/제3보험) the product most likely belongs to. The result
   is constrained to a fixed enum, so the model cannot hallucinate a category
   outside the known buckets. Any failure (missing API key, network error,
   validation error) degrades to CLASSIFICATION_UNKNOWN — this function never
   raises.

Both tiers finish with the same tag-enrichment pass: `tag_terms` presence
checks over the same search space, deduplicated and sorted by `tag_order`.

The result is UI-oriented display metadata for browsing policies, not a legal
determination of insurance category.
"""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.services.llm import JsonCompleter, structured_completer
from app.services.types import PolicyClassification

CLASSIFICATION_UNKNOWN = "미분류"

_HEAD_CHARS = 3_000

_RULES_PATH = Path(__file__).with_name("data") / "classification_rules.json"
_RAW_RULES = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
TAG_ORDER: list[str] = _RAW_RULES["tag_order"]

_ClassificationLiteral = Literal[
    "자동차", "상해·질병·실손", "배상·화재·기타", "생명·연금", "미분류"
]

_SYSTEM = (
    "너는 보험 상품을 보험업법 제4조가 정하는 보험종목 구분(생명보험/손해보험/제3보험)에 "
    "따라 분류하는 도우미다. "
    "입력은 상품명과 증권 앞부분 텍스트다. "
    "다음 네 범주 중 가장 알맞은 하나를 고르라: "
    "'자동차'(자동차보험), "
    "'상해·질병·실손'(제3보험 성격의 상해·질병·실손의료보험), "
    "'배상·화재·기타'(운전자보험·화재보험·배상책임보험 등 그 외 손해보험), "
    "'생명·연금'(생명보험·연금보험). "
    "근거가 부족해 판단할 수 없으면 '미분류'를 반환하라. 지어내지 마라."
)


class _ClassificationResult(BaseModel):
    보험분류: _ClassificationLiteral


def _normalize_text(value: str) -> str:
    return "".join(value.split()).lower()


def _normalize_terms(terms: list[str]) -> list[str]:
    return [_normalize_text(term) for term in terms]


@dataclass(frozen=True)
class _Category:
    classification: str
    terms: list[str]


_CATEGORIES = [
    _Category(
        classification=category["classification"],
        terms=_normalize_terms(category["terms"]),
    )
    for category in _RAW_RULES["categories"]
]

_TAG_TERMS: dict[str, list[str]] = {
    tag: _normalize_terms(terms) for tag, terms in _RAW_RULES["tag_terms"].items()
}


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _search_space(text: str, product_name: str | None) -> str:
    normalized_text = _normalize_text(text)[:_HEAD_CHARS]
    normalized_product_name = _normalize_text(product_name or "")
    return f"{normalized_product_name}\n{normalized_text}".strip()


def _enrich_tags(classification: str, search_space: str) -> PolicyClassification:
    tags_found = {tag for tag, terms in _TAG_TERMS.items() if _contains_any(search_space, terms)}
    tags = [tag for tag in TAG_ORDER if tag in tags_found]
    return {"보험분류": classification, "상품태그": tags}


def _match_deterministic(search_space: str) -> str | None:
    for category in _CATEGORIES:
        if _contains_any(search_space, category.terms):
            return category.classification
    return None


@lru_cache
def _default_completer() -> JsonCompleter:
    return structured_completer(_ClassificationResult)


def _classify_with_llm(source: str, complete: JsonCompleter | None) -> str:
    completer = complete or _default_completer()
    try:
        payload = completer(_SYSTEM, source)
        return _ClassificationResult.model_validate(payload).보험분류
    except Exception:
        return CLASSIFICATION_UNKNOWN


def classify_policy(
    text: str,
    product_name: str | None = None,
    complete: JsonCompleter | None = None,
) -> PolicyClassification:
    search_space = _search_space(text, product_name)

    classification = _match_deterministic(search_space)
    if classification is None:
        classification = _classify_with_llm(search_space, complete)

    if classification == CLASSIFICATION_UNKNOWN:
        return {"보험분류": CLASSIFICATION_UNKNOWN, "상품태그": []}

    return _enrich_tags(classification, search_space)
