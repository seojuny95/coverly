import json
from pathlib import Path
from typing import TypedDict


class PolicyClassification(TypedDict):
    보험분류: str
    상품태그: list[str]


CLASSIFICATION_UNKNOWN = "미분류"

_RULES_PATH = Path(__file__).with_name("policy_classification_rules.json")
_RAW_RULES = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
TAG_ORDER: list[str] = _RAW_RULES["tag_order"]

# The classification buckets are UI-oriented groupings for policy browsing.
# They are not legal determinations.
# Rules are based on recurring product and coverage terms in insurer documents.
# Terminology follows public naming used by regulators, associations, product pages,
# and statutes.


def _normalize_text(value: str) -> str:
    return "".join(value.split()).lower()


def _normalize_terms(terms: list[str]) -> list[str]:
    return [_normalize_text(term) for term in terms]


def _normalize_tag_terms(tag_terms: dict[str, list[str]]) -> dict[str, list[str]]:
    return {tag: _normalize_terms(terms) for tag, terms in tag_terms.items()}


_CLASSIFICATION_RULES = {
    "auto": {
        **_RAW_RULES["rules"]["auto"],
        "product_terms": _normalize_terms(_RAW_RULES["rules"]["auto"]["product_terms"]),
        "coverage_terms": _normalize_terms(_RAW_RULES["rules"]["auto"]["coverage_terms"]),
    },
    "driver": {
        **_RAW_RULES["rules"]["driver"],
        "product_terms": _normalize_terms(_RAW_RULES["rules"]["driver"]["product_terms"]),
        "coverage_terms": _normalize_terms(_RAW_RULES["rules"]["driver"]["coverage_terms"]),
    },
    "indemnity": {
        **_RAW_RULES["rules"]["indemnity"],
        "terms": _normalize_terms(_RAW_RULES["rules"]["indemnity"]["terms"]),
    },
    "fire": {
        **_RAW_RULES["rules"]["fire"],
        "product_terms": _normalize_terms(_RAW_RULES["rules"]["fire"]["product_terms"]),
        "coverage_terms": _normalize_terms(_RAW_RULES["rules"]["fire"]["coverage_terms"]),
        "liability_terms": _normalize_terms(_RAW_RULES["rules"]["fire"]["liability_terms"]),
    },
    "life": {
        **_RAW_RULES["rules"]["life"],
        "tag_terms": _normalize_tag_terms(_RAW_RULES["rules"]["life"]["tag_terms"]),
    },
    "health": {
        **_RAW_RULES["rules"]["health"],
        "tag_terms": _normalize_tag_terms(_RAW_RULES["rules"]["health"]["tag_terms"]),
    },
}


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _count_matches(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term in text)


def _add_tag(tags: list[str], tag: str) -> None:
    if tag not in tags:
        tags.append(tag)


def classify_policy(
    text: str,
    product_name: str | None = None,
) -> PolicyClassification:
    auto_rule = _CLASSIFICATION_RULES["auto"]
    driver_rule = _CLASSIFICATION_RULES["driver"]
    indemnity_rule = _CLASSIFICATION_RULES["indemnity"]
    fire_rule = _CLASSIFICATION_RULES["fire"]
    life_rule = _CLASSIFICATION_RULES["life"]
    health_rule = _CLASSIFICATION_RULES["health"]

    normalized_text = _normalize_text(text)
    normalized_product_name = _normalize_text(product_name or "")
    search_space = f"{normalized_product_name}\n{normalized_text}".strip()
    tags: list[str] = []

    auto_strength = _count_matches(
        search_space,
        auto_rule["product_terms"],
    )
    auto_strength += _count_matches(
        normalized_text,
        auto_rule["coverage_terms"],
    )

    driver_product_hits = _count_matches(
        normalized_product_name,
        driver_rule["product_terms"],
    )
    driver_strength = driver_product_hits * driver_rule["product_weight"]
    driver_strength += _count_matches(
        normalized_text,
        driver_rule["coverage_terms"],
    )

    indemnity_strength = _count_matches(
        normalized_text,
        indemnity_rule["terms"],
    )
    if normalized_product_name and _contains_any(normalized_product_name, indemnity_rule["terms"]):
        indemnity_strength += indemnity_rule["product_bonus"]

    fire_product_hits = _count_matches(
        normalized_product_name,
        fire_rule["product_terms"],
    )
    fire_strength = fire_product_hits * fire_rule["product_weight"]
    fire_strength += _count_matches(
        normalized_text,
        fire_rule["coverage_terms"],
    )
    liability_strength = _count_matches(
        normalized_text,
        fire_rule["liability_terms"],
    )

    life_tags_found: list[str] = []
    for tag, terms in life_rule["tag_terms"].items():
        if _contains_any(normalized_product_name, terms):
            life_tags_found.append(tag)

    health_tags_found: list[str] = []
    for tag, terms in health_rule["tag_terms"].items():
        if _contains_any(search_space, terms):
            health_tags_found.append(tag)

    if driver_strength >= driver_rule["min_strength"]:
        for tag in driver_rule["tags"]:
            _add_tag(tags, tag)
        return {
            "보험분류": driver_rule["classification"],
            "상품태그": tags,
        }

    if auto_strength >= auto_rule["min_strength"]:
        for tag in auto_rule["tags"]:
            _add_tag(tags, tag)
        return {
            "보험분류": auto_rule["classification"],
            "상품태그": tags,
        }

    if life_tags_found:
        for tag in TAG_ORDER:
            if tag in life_tags_found:
                _add_tag(tags, tag)
        return {
            "보험분류": life_rule["classification"],
            "상품태그": tags,
        }

    if indemnity_strength >= indemnity_rule["min_strength"]:
        for tag in indemnity_rule["tags"]:
            _add_tag(tags, tag)
        return {
            "보험분류": indemnity_rule["classification"],
            "상품태그": tags,
        }

    if (
        fire_product_hits >= fire_rule["min_product_hits"]
        or (fire_strength + liability_strength) >= fire_rule["min_combined_strength"]
    ):
        for tag in fire_rule["base_tags"]:
            _add_tag(tags, tag)
        if liability_strength >= 1:
            _add_tag(tags, fire_rule["liability_tag"])
        return {
            "보험분류": fire_rule["classification"],
            "상품태그": tags,
        }

    if liability_strength >= 2:
        _add_tag(tags, fire_rule["liability_tag"])
        return {
            "보험분류": fire_rule["classification"],
            "상품태그": tags,
        }

    if health_tags_found:
        for tag in TAG_ORDER:
            if tag in health_tags_found:
                _add_tag(tags, tag)
        return {
            "보험분류": health_rule["classification"],
            "상품태그": tags,
        }

    return {
        "보험분류": CLASSIFICATION_UNKNOWN,
        "상품태그": tags,
    }
