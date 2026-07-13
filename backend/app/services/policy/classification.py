"""Classify a policy into a display bucket and enrich it with product tags.

Two tiers, in order:

1. Deterministic mapping — `classification_rules.json` lists categories in
   priority order, each with official 보험종목 terms (e.g. "자동차보험",
   "종신보험"). The first category whose terms appear in the normalized
   product name wins. Only the product name is consulted: body text is
   structurally noisy (insurer legal names and coverage mentions contain
   official terms). No scores, weights, or thresholds — term presence only.
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
from typing import Literal

from pydantic import BaseModel

from app.services.llm import JsonCompleter, structured_completer
from app.services.paths import SERVICE_DATA_DIR
from app.services.policy.models import PolicyClassification

CLASSIFICATION_UNKNOWN = "미분류"

_HEAD_CHARS = 3_000

_RULES_PATH = SERVICE_DATA_DIR / "classification_rules.json"
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
    "'상해·질병·실손'(제3보험 성격의 상해·질병·간병·실손의료보험 — 진단비·수술비·입원일당 "
    "중심의 건강·어린이 상품 포함), "
    "'배상·화재·기타'(운전자보험·화재보험·배상책임보험 등 그 외 손해보험), "
    "'생명·연금'(사망보장 중심의 생명보험·연금보험). "
    "겸영 금지 규칙을 지켜라: 손해보험사(회사명에 화재·해상·손해보험 포함)의 상품은 "
    "'생명·연금'이 될 수 없고, 생명보험사(회사명에 생명 포함)의 상품은 "
    "'자동차'나 '배상·화재·기타'가 될 수 없다. "
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
    tags: list[str]
    terms: list[str]


_CATEGORIES = [
    _Category(
        classification=category["classification"],
        tags=category["tags"],
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
    # Pre-truncate before normalizing so a large PDF does not pay a full-text
    # pass for a 3,000-char head; 2x covers whitespace removed by normalization.
    normalized_text = _normalize_text(text[: _HEAD_CHARS * 2])[:_HEAD_CHARS]
    normalized_product_name = _normalize_text(product_name or "")
    return f"{normalized_product_name}\n{normalized_text}".strip()


def _enrich_tags(
    classification: str,
    search_space: str,
    seed_tags: list[str] | None = None,
) -> PolicyClassification:
    """Tags = the matched category's own tags plus every tag_terms hit, in TAG_ORDER."""
    tags_found = set(seed_tags or [])
    for tag, terms in _TAG_TERMS.items():
        if _contains_any(search_space, terms):
            tags_found.add(tag)

    tags = [tag for tag in TAG_ORDER if tag in tags_found]
    return {"보험분류": classification, "상품태그": tags}


def _match_deterministic(product_name: str | None) -> _Category | None:
    """First category whose official terms appear in the product name.

    Only the product name is trusted for deterministic matching: body text is
    structurally noisy — insurer legal names ("흥국화재…", "…생명보험") and mere
    coverage mentions ("실손의료비") contain official terms without the policy
    being that product. Anything the product name cannot settle goes to the
    LLM fallback instead of a fuzzier rule.
    """
    product_space = _normalize_text(product_name or "")
    if not product_space:
        return None

    for category in _CATEGORIES:
        if _contains_any(product_space, category.terms):
            return category

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

    category = _match_deterministic(product_name)
    if category is not None:
        return _enrich_tags(category.classification, search_space, seed_tags=category.tags)

    classification = _classify_with_llm(search_space, complete)
    if classification == CLASSIFICATION_UNKNOWN:
        return {"보험분류": CLASSIFICATION_UNKNOWN, "상품태그": []}

    return _enrich_tags(classification, search_space)
