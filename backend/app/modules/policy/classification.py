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

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, cast

from pydantic import BaseModel

from app.integrations.openai import JsonCompleter, structured_completer
from app.modules.policy.models import PolicyClassification
from app.modules.reference_data import REFERENCE_DATA_DIR, load_reference_data

CLASSIFICATION_UNKNOWN = "미분류"

_HEAD_CHARS = 3_000

_RULES_PATH = REFERENCE_DATA_DIR / "classification_rules.json"

_ClassificationLiteral = Literal["생명보험", "제3보험", "손해보험", "미분류"]

_SYSTEM = (
    "# 역할\n"
    "너는 한국 보험 상품을 표시용 보험분류로 보수적으로 분류하는 도우미다.\n\n"
    "# 목표\n"
    "상품명과 증권 앞부분 텍스트만 근거로, 가장 알맞은 보험분류 하나를 선택한다. "
    "근거가 부족하면 미분류를 선택한다.\n\n"
    "# 선택 가능한 보험분류\n"
    "1. 생명보험: 사람의 사망·노후 보장을 중심으로 하는 종신보험, 정기보험, "
    "연금보험, 양로보험, 저축보험.\n"
    "2. 제3보험: 사람의 질병·상해·간병 보장을 중심으로 하는 질병보험, 상해보험, "
    "간병보험, 실손의료보험, 어린이보험.\n"
    "3. 손해보험: 사고로 인한 재산 손해나 법적 책임을 중심으로 하는 자동차보험, "
    "운전자보험, 여행자보험, 화재보험, 배상책임보험, 보증보험.\n"
    "4. 미분류: 위 범주 중 하나로 판단할 근거가 부족한 경우.\n\n"
    "# 작업 순서\n"
    "1. 상품명에 명확한 보험종목 단서가 있는지 먼저 확인한다.\n"
    "2. 상품명이 부족하면 증권 앞부분 텍스트에서 회사명, 보장 성격, 상품 설명 단서를 확인한다.\n"
    "3. 겸영 금지 규칙과 충돌하는 분류를 제거한다.\n"
    "4. 남은 후보 중 근거가 가장 명확한 하나를 선택한다.\n"
    "5. 충분한 근거가 없거나 후보가 충돌하면 미분류를 반환한다.\n\n"
    "# 해야 할 것\n"
    "- 상품명 단서를 본문 단서보다 우선한다.\n"
    "- 손해보험사(회사명에 화재·해상·손해보험 포함)의 상품은 생명보험으로 분류하지 않는다.\n"
    "- 생명보험사(회사명에 생명 포함)의 상품은 손해보험으로 분류하지 않는다.\n"
    "- 어린이/건강/진단비/수술비/입원일당 중심 상품은 제3보험 후보로 검토한다.\n\n"
    "# 하지 말아야 할 것\n"
    "- 운전자보험이나 운전자상해보험을 자동차보험 태그로 분류하지 않는다.\n"
    "- 자동차부상치료비, 교통사고처리지원금 같은 운전자보험 담보명만 보고 "
    "자동차로 분류하지 않는다.\n"
    "- 단순히 본문에 담보명이 한 번 나온 것만으로 상품 전체 분류를 바꾸지 않는다.\n"
    "- 회사명이나 브랜드명만 보고 상품 성격을 지어내지 않는다.\n"
    "- 근거가 부족한데 억지로 네 주요 범주 중 하나를 고르지 않는다."
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


def _validate_rules_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("classification rules must be an object")
    if not isinstance(value.get("categories"), list):
        raise ValueError("classification rules must contain categories")
    if not isinstance(value.get("tag_order"), list):
        raise ValueError("classification rules must contain tag_order")
    if not isinstance(value.get("tag_terms"), dict):
        raise ValueError("classification rules must contain tag_terms")
    return cast(dict[str, Any], value)


_RAW_RULES = load_reference_data("classification_rules", _RULES_PATH, _validate_rules_payload)
TAG_ORDER: list[str] = _RAW_RULES["tag_order"]
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
_DAMAGE_GENERAL_PRODUCT_TERMS = _normalize_terms(["생활종합보험", "종합손해보험"])
_DAMAGE_GENERAL_CONTEXT_TERMS = _normalize_terms(
    ["화재", "배상", "벌금", "고장수리", "소재지", "주택", "아파트", "가재", "재물"]
)


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
    tag_space: str,
    seed_tags: list[str] | None = None,
) -> PolicyClassification:
    """Tags = insurance type terms found around product identity, in TAG_ORDER."""
    tags_found = set(seed_tags or [])
    for tag, terms in _TAG_TERMS.items():
        if _contains_any(tag_space, terms):
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


def _match_contextual(search_space: str, product_name: str | None) -> _Category | None:
    """Classify broad non-life package products only with product + context evidence."""

    product_space = _normalize_text(product_name or "")
    if not _contains_any(product_space, _DAMAGE_GENERAL_PRODUCT_TERMS):
        return None
    if not _contains_any(search_space, _DAMAGE_GENERAL_CONTEXT_TERMS):
        return None

    return _Category(classification="손해보험", tags=[], terms=[])


@lru_cache
def _default_completer() -> JsonCompleter:
    return structured_completer(_ClassificationResult)


def _classify_with_llm(source: str, complete: JsonCompleter | None) -> str:
    completer = complete or _default_completer()
    try:
        payload = completer(_SYSTEM, _classification_user_prompt(source))
        return _ClassificationResult.model_validate(payload).보험분류
    except Exception:
        return CLASSIFICATION_UNKNOWN


def _classification_user_prompt(source: str) -> str:
    return (
        "# 입력\n"
        "아래 텍스트는 상품명과 증권 앞부분 텍스트를 합친 것이다.\n\n"
        "# 분류 대상 텍스트\n"
        f"{source}"
    )


def classify_policy(
    text: str,
    product_name: str | None = None,
    complete: JsonCompleter | None = None,
) -> PolicyClassification:
    search_space = _search_space(text, product_name)
    tag_space = _normalize_text(product_name or "")

    category = _match_deterministic(product_name)
    if category is not None:
        return _enrich_tags(category.classification, tag_space, seed_tags=category.tags)

    category = _match_contextual(search_space, product_name)
    if category is not None:
        return _enrich_tags(category.classification, tag_space, seed_tags=category.tags)

    classification = _classify_with_llm(search_space, complete)
    if classification == CLASSIFICATION_UNKNOWN:
        return {"보험분류": CLASSIFICATION_UNKNOWN, "상품태그": []}

    return _enrich_tags(classification, tag_space)
