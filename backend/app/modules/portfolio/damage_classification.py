"""Canonical auto and fire policy classification for portfolio consumers."""

from typing import Literal

from app.modules.coverage.indemnity import is_damage_policy_context
from app.modules.portfolio.amounts import normalize, normalized_terms
from app.modules.portfolio.schemas import PolicyInput

AutoPolicyMatchSource = Literal["identity", "coverage"]

AUTO_LIABILITY_INJURY_TERMS = ("대인배상",)
AUTO_LIABILITY_PROPERTY_TERMS = ("대물배상",)
AUTO_OCCUPANT_INJURY_TERMS = ("자동차상해", "자기신체사고", "자손")
AUTO_VEHICLE_DAMAGE_TERMS = ("자기차량손해", "자기차량", "자차")
AUTO_UNINSURED_INJURY_TERMS = ("무보험자동차", "무보험차상해", "무보험차에의한상해")
AUTO_POLICY_COVERAGE_TERMS = tuple(
    dict.fromkeys(
        (
            *AUTO_LIABILITY_INJURY_TERMS,
            *AUTO_LIABILITY_PROPERTY_TERMS,
            *AUTO_OCCUPANT_INJURY_TERMS,
            *AUTO_VEHICLE_DAMAGE_TERMS,
            *AUTO_UNINSURED_INJURY_TERMS,
        )
    )
)
AUTO_PRODUCT_TERMS = (
    "자동차보험",
    "개인용자동차",
    "업무용자동차",
    "영업용자동차",
    "다이렉트자동차",
    "하이카",
)

FIRE_PROPERTY_DAMAGE_TERMS = ("화재손해", "건물화재", "가재화재", "주택화재")
FIRE_LIABILITY_TERMS = ("화재배상책임", "화재대물배상", "화재대인배상", "폭발포함배상책임")
FIRE_RECOVERY_COST_TERMS = ("임시거주", "잔존물제거", "화재복구", "복구비용")
FIRE_POLICY_COVERAGE_TERMS = tuple(
    dict.fromkeys(
        (
            *FIRE_PROPERTY_DAMAGE_TERMS,
            *FIRE_LIABILITY_TERMS,
            *FIRE_RECOVERY_COST_TERMS,
            "화재폭발",
        )
    )
)
FIRE_PRODUCT_TERMS = (
    "화재보험",
    "주택화재보험",
    "주택종합보험",
    "재물보험",
)

DAMAGE_INSURANCE_TYPE_ORDER = (
    "자동차보험",
    "운전자보험",
    "여행자보험",
    "화재보험",
    "배상책임보험",
    "보증보험",
    "손해보험",
)
_DAMAGE_CATEGORY_TYPES = {
    "자동차": "자동차보험",
    "자동차보험": "자동차보험",
    "운전자보험": "운전자보험",
    "운전자상해보험": "운전자보험",
    "여행자보험": "여행자보험",
    "화재보험": "화재보험",
    "주택화재보험": "화재보험",
    "배상책임보험": "배상책임보험",
    "보증보험": "보증보험",
}
_NORMALIZED_AUTO_CATEGORY_TERM = normalize("자동차보험")
_NORMALIZED_AUTO_TAG_TERM = normalize("자동차")
_NORMALIZED_AUTO_PRODUCT_TERMS = normalized_terms(AUTO_PRODUCT_TERMS)
_NORMALIZED_AUTO_POLICY_COVERAGE_TERMS = normalized_terms(AUTO_POLICY_COVERAGE_TERMS)
_NORMALIZED_FIRE_CATEGORIES = {normalize("화재보험"), normalize("주택화재보험")}
_NORMALIZED_FIRE_PRODUCT_TERMS = normalized_terms(FIRE_PRODUCT_TERMS)
_NORMALIZED_FIRE_POLICY_COVERAGE_TERMS = normalized_terms(FIRE_POLICY_COVERAGE_TERMS)


def auto_policy_match_source(policy: PolicyInput) -> AutoPolicyMatchSource | None:
    category, product, tags, coverage_names = _normalized_identity(policy)
    if (
        _NORMALIZED_AUTO_CATEGORY_TERM in category
        or any(term in product for term in _NORMALIZED_AUTO_PRODUCT_TERMS)
        or any(_NORMALIZED_AUTO_TAG_TERM in tag for tag in tags)
    ):
        return "identity"
    if not is_damage_policy_context(policy):
        return None
    if _contains_any_coverage(coverage_names, _NORMALIZED_AUTO_POLICY_COVERAGE_TERMS):
        return "coverage"
    return None


def is_auto_policy(policy: PolicyInput) -> bool:
    return auto_policy_match_source(policy) is not None


def is_fire_policy(policy: PolicyInput) -> bool:
    category, product, tags, coverage_names = _normalized_identity(policy)
    if category in _NORMALIZED_FIRE_CATEGORIES or any(
        tag in _NORMALIZED_FIRE_CATEGORIES for tag in tags
    ):
        return True
    if any(term in product for term in _NORMALIZED_FIRE_PRODUCT_TERMS):
        return True
    return is_damage_policy_context(policy) and _contains_any_coverage(
        coverage_names,
        _NORMALIZED_FIRE_POLICY_COVERAGE_TERMS,
    )


def damage_insurance_type(policy: PolicyInput) -> str:
    category = policy.기본정보.보험분류 or ""
    if category in _DAMAGE_CATEGORY_TYPES:
        return _DAMAGE_CATEGORY_TYPES[category]

    tags = policy.기본정보.상품태그
    for insurance_type in DAMAGE_INSURANCE_TYPE_ORDER:
        if insurance_type in tags:
            return insurance_type

    if is_auto_policy(policy):
        return "자동차보험"
    if is_fire_policy(policy):
        return "화재보험"

    normalized_product = normalize(policy.기본정보.상품명 or "")
    for insurance_type in DAMAGE_INSURANCE_TYPE_ORDER:
        if normalize(insurance_type) in normalized_product:
            return insurance_type
    return "손해보험"


def _normalized_identity(
    policy: PolicyInput,
) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    return (
        normalize(policy.기본정보.보험분류 or ""),
        normalize(policy.기본정보.상품명 or ""),
        tuple(normalize(tag) for tag in policy.기본정보.상품태그),
        tuple(normalize(coverage.담보명) for coverage in policy.보장목록),
    )


def _contains_any_coverage(
    coverage_names: tuple[str, ...],
    normalized_rule_terms: tuple[str, ...],
) -> bool:
    return any(any(term in name for term in normalized_rule_terms) for name in coverage_names)
