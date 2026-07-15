"""Deterministic indemnity classification helpers.

Korean insurance copy uses "실손" both for medical indemnity insurance and for
generic actual-loss reimbursement. This module keeps those concepts separate.
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.schemas.portfolio import CoverageInput, PolicyInput

PaymentBasis = Literal["fixed", "indemnity", "unknown"]
CoverageDomain = Literal[
    "medical_expense",
    "legal_cost",
    "property_damage",
    "liability",
    "auto",
    "other",
]
MedicalIndemnityStatus = Literal["confirmed", "excluded", "unknown"]


@dataclass(frozen=True)
class IndemnityClassification:
    payment_basis: PaymentBasis
    coverage_domain: CoverageDomain
    medical_indemnity_status: MedicalIndemnityStatus


_FIXED_PAYMENT_TYPES = frozenset({"정액", "정액형", "고정액", "고정액형"})
_INDEMNITY_PAYMENT_TYPES = frozenset(
    {
        "실손",
        "실손형",
        "실비",
        "실비형",
        "비례",
        "비례형",
        "비례보상",
        "실액",
        "실액형",
        "실액보상",
    }
)
_INDEMNITY_CATEGORIES = frozenset({"실손", "실손형", "실비", "실비형"})
_INDEMNITY_NAME_TERMS = ("실손", "실비")
_NEGATED_INDEMNITY_PATTERNS = (
    "비실손",
    "비실비",
    "실손제외",
    "실비제외",
    "실손미해당",
    "실비미해당",
    "실손아님",
    "실비아님",
    "실손비대상",
    "실비비대상",
    "실손미포함",
    "실비미포함",
)
_MEDICAL_TERMS = (
    "실손의료",
    "실손의료비",
    "실손보험",
    "실비보험",
    "의료비",
    "입원의료비",
    "통원의료비",
    "처방조제",
    "처방조제비",
    "약제비",
    "병원비",
    "치료비",
    "상해실비",
    "질병실비",
    "상해실손",
    "질병실손",
)
_LEGAL_TERMS = ("벌금", "변호사", "교통사고처리지원금", "형사합의", "방어비용")
_PROPERTY_TERMS = (
    "화재",
    "붕괴",
    "침강",
    "사태",
    "풍수재",
    "대설",
    "급배수",
    "누출",
    "가재",
    "건물",
    "재조달",
    "수리비",
    "고장수리",
    "휴대품손해",
)
_LIABILITY_TERMS = ("배상책임", "대물", "대인", "손해배상")
_AUTO_TERMS = ("자동차", "자가용", "운전자", "교통사고", "비탑승")
_DAMAGE_TAG_TERMS = (
    "자동차보험",
    "운전자보험",
    "여행자보험",
    "화재보험",
    "주택화재보험",
    "배상책임보험",
    "보증보험",
)


def classify_indemnity(
    coverage: CoverageInput,
    *,
    policy: PolicyInput | None = None,
) -> IndemnityClassification:
    """Classify actual-loss reimbursement separately from medical indemnity."""

    text = _coverage_text(coverage, policy)
    payment_basis = _payment_basis(coverage)
    domain = _coverage_domain(text, policy)
    medical_status: MedicalIndemnityStatus

    if domain == "medical_expense" and (
        payment_basis == "indemnity" or _contains_any(text, _INDEMNITY_NAME_TERMS)
    ):
        medical_status = "confirmed"
    elif domain != "medical_expense" and (
        payment_basis == "indemnity" or _contains_any(text, _INDEMNITY_NAME_TERMS)
    ):
        medical_status = "excluded"
    else:
        medical_status = "unknown"

    return IndemnityClassification(
        payment_basis=payment_basis,
        coverage_domain=domain,
        medical_indemnity_status=medical_status,
    )


def is_medical_indemnity_name(name: str) -> bool:
    """Return whether a standalone coverage name means medical indemnity."""

    normalized = _normalize(name)
    return _contains_any(normalized, _MEDICAL_TERMS) and _contains_any(
        normalized, _INDEMNITY_NAME_TERMS
    )


def _payment_basis(coverage: CoverageInput) -> PaymentBasis:
    payment_type = (coverage.지급유형 or "").strip()
    if payment_type in _INDEMNITY_PAYMENT_TYPES:
        return "indemnity"
    if payment_type in _FIXED_PAYMENT_TYPES:
        return "fixed"
    if payment_type:
        return "unknown"

    coverage_category = (coverage.보장분류 or "").strip()
    normalized_name = _normalize(coverage.담보명)
    normalized_category = _normalize(coverage_category)
    if any(
        pattern in normalized_name or pattern in normalized_category
        for pattern in _NEGATED_INDEMNITY_PATTERNS
    ):
        return "unknown"
    if coverage_category in _INDEMNITY_CATEGORIES:
        return "indemnity"
    if _contains_any(normalized_name, _INDEMNITY_NAME_TERMS):
        return "indemnity"
    return "unknown"


def _coverage_domain(text: str, policy: PolicyInput | None) -> CoverageDomain:
    if _is_damage_policy(policy):
        if _contains_any(text, _AUTO_TERMS):
            return "auto"
        if _contains_any(text, _LEGAL_TERMS):
            return "legal_cost"
        if _contains_any(text, _LIABILITY_TERMS):
            return "liability"
        if _contains_any(text, _PROPERTY_TERMS):
            return "property_damage"

    if _contains_any(text, _LEGAL_TERMS):
        return "legal_cost"
    if _contains_any(text, _LIABILITY_TERMS):
        return "liability"
    if _contains_any(text, _AUTO_TERMS):
        return "auto"
    if _contains_any(text, _PROPERTY_TERMS):
        return "property_damage"
    if _contains_any(text, _MEDICAL_TERMS):
        return "medical_expense"
    return "other"


def _coverage_text(coverage: CoverageInput, policy: PolicyInput | None) -> str:
    parts = [
        coverage.담보명,
        coverage.보장분류 or "",
        coverage.지급유형 or "",
        coverage.보장내용 or "",
        coverage.해설 or "",
    ]
    if policy is not None:
        parts.extend(
            [
                policy.기본정보.보험분류 or "",
                policy.기본정보.상품명 or "",
                *policy.기본정보.상품태그,
            ]
        )
    return _normalize(" ".join(parts))


def _is_damage_policy(policy: PolicyInput | None) -> bool:
    if policy is None:
        return False
    category = policy.기본정보.보험분류 or ""
    tags = policy.기본정보.상품태그
    return category == "손해보험" or any(tag in _DAMAGE_TAG_TERMS for tag in tags)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_normalize(term) in text for term in terms)


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()
