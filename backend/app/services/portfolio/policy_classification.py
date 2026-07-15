"""Shared policy classification helpers for portfolio use cases."""

import re

from app.schemas.portfolio import PolicyInput

_DAMAGE_CLASSIFICATION = "손해보험"
_LEGACY_DAMAGE_CLASSIFICATIONS = frozenset(
    {
        "자동차",
        "자동차보험",
        "운전자보험",
        "운전자상해보험",
        "여행자보험",
        "화재보험",
        "주택화재보험",
        "배상책임보험",
        "보증보험",
        "배상·화재·기타",
    }
)
_AUTO_TAG_TERMS = ("자동차", "자동차보험")
_DAMAGE_INSURANCE_TYPE_ORDER = (
    "자동차보험",
    "운전자보험",
    "여행자보험",
    "화재보험",
    "배상책임보험",
    "보증보험",
    "손해보험",
)


def is_damage_policy(policy: PolicyInput) -> bool:
    """Return whether a policy belongs to the separately handled non-life branch."""

    category = policy.기본정보.보험분류 or ""
    return category == _DAMAGE_CLASSIFICATION or category in _LEGACY_DAMAGE_CLASSIFICATIONS


def is_auto_policy(policy: PolicyInput) -> bool:
    """Return whether a policy is an auto policy inside the damage branch."""

    return any(term in damage_insurance_type(policy) for term in _AUTO_TAG_TERMS)


def damage_insurance_type(policy: PolicyInput) -> str:
    """Return the display category for a non-life policy."""

    category = policy.기본정보.보험분류 or ""
    if category in {"자동차", "자동차보험"}:
        return "자동차보험"
    if category in {"운전자보험", "운전자상해보험"}:
        return "운전자보험"
    if category == "여행자보험":
        return "여행자보험"
    if category in {"화재보험", "주택화재보험"}:
        return "화재보험"
    if category == "배상책임보험":
        return "배상책임보험"
    if category == "보증보험":
        return "보증보험"

    tags = policy.기본정보.상품태그
    for insurance_type in _DAMAGE_INSURANCE_TYPE_ORDER:
        if insurance_type in tags:
            return insurance_type

    normalized_product = _normalize_label(policy.기본정보.상품명 or "")
    for insurance_type in _DAMAGE_INSURANCE_TYPE_ORDER:
        if _normalize_label(insurance_type) in normalized_product:
            return insurance_type

    return "손해보험"


def damage_insurance_type_rank(insurance_type: str) -> tuple[int, str]:
    """Return a stable display order for non-life policy groups."""

    try:
        return (_DAMAGE_INSURANCE_TYPE_ORDER.index(insurance_type), insurance_type)
    except ValueError:
        return (len(_DAMAGE_INSURANCE_TYPE_ORDER), insurance_type)


def _normalize_label(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()
