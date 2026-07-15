"""Deterministic classification for indemnity-style coverages.

This separates payment basis from coverage domain. A coverage can be paid on
an indemnity basis without being 실손의료보험.
"""

import re
from dataclasses import dataclass
from typing import Literal

PaymentBasis = Literal["fixed", "indemnity", "unknown"]
CoverageDomain = Literal[
    "medical_expense",
    "property_damage",
    "liability",
    "legal_cost",
    "driver",
    "travel",
    "other",
    "unknown",
]
MedicalIndemnityStatus = Literal["confirmed", "candidate", "not_applicable", "unknown"]


@dataclass(frozen=True)
class IndemnityClassification:
    payment_basis: PaymentBasis
    coverage_domain: CoverageDomain
    medical_indemnity_status: MedicalIndemnityStatus


FIXED_PAYMENT_TYPES = frozenset({"정액", "정액형", "고정액", "고정액형"})
INDEMNITY_PAYMENT_TYPES = frozenset(
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

_NEGATED_INDEMNITY_TERMS = (
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
_INDEMNITY_TERMS = ("실손", "실비", "비례보상", "실액보상")
_MEDICAL_TERMS = (
    "실손의료",
    "실손의료비",
    "실손보험",
    "실비보험",
    "상해실손",
    "질병실손",
    "상해실비",
    "질병실비",
    "의료비",
    "입원의료비",
    "통원의료비",
    "해외의료비",
    "해외실손의료비",
    "국외의료비",
    "급여",
    "비급여",
    "자기부담금",
    "공제금액",
)
_PROPERTY_TERMS = (
    "화재",
    "붕괴",
    "침강",
    "사태",
    "풍수재",
    "수재",
    "지진",
    "대설",
    "건물",
    "가재",
    "도구",
    "휴대품",
    "고장수리",
    "급배수",
    "누출",
    "재조달",
    "폐기물",
    "임시거주",
)
_LIABILITY_TERMS = ("배상책임", "대인배상", "대물배상")
_LEGAL_COST_TERMS = ("벌금", "변호사", "변호사선임", "형사합의", "처리지원금")
_DRIVER_TERMS = ("운전자", "교통사고", "자동차사고")
_TRAVEL_TERMS = ("여행", "항공기", "항공편")


def classify_indemnity(
    *,
    coverage_name: str,
    payment_type: str | None = None,
    coverage_category: str | None = None,
    coverage_description: str | None = None,
    product_name: str | None = None,
    policy_classification: str | None = None,
    product_tags: list[str] | tuple[str, ...] = (),
) -> IndemnityClassification:
    """Classify indemnity semantics from structured fields and conservative text cues."""

    text = _combined_text(
        coverage_name,
        coverage_category,
        coverage_description,
        product_name,
        policy_classification,
        *product_tags,
    )
    payment_basis = _payment_basis(
        coverage_name=coverage_name,
        payment_type=payment_type,
        coverage_category=coverage_category,
        text=text,
    )
    domain = _coverage_domain(text)

    if domain != "medical_expense":
        status: MedicalIndemnityStatus = "not_applicable"
    elif payment_basis == "indemnity" or _has_product_level_medical_indemnity(text):
        status = "confirmed"
    elif _has_medical_term(text):
        status = "candidate"
    else:
        status = "unknown"

    return IndemnityClassification(
        payment_basis=payment_basis,
        coverage_domain=domain,
        medical_indemnity_status=status,
    )


def is_medical_indemnity_text(value: str) -> bool:
    """Return True when standalone text clearly points to medical indemnity."""

    text = normalize_insurance_text(value)
    return _coverage_domain(text) == "medical_expense"


def has_negated_indemnity_text(value: str) -> bool:
    """Return True when text explicitly says indemnity does not apply."""

    text = normalize_insurance_text(value)
    return any(term in text for term in _NEGATED_INDEMNITY_TERMS)


def _payment_basis(
    *,
    coverage_name: str,
    payment_type: str | None,
    coverage_category: str | None,
    text: str,
) -> PaymentBasis:
    payment = (payment_type or "").strip()
    if payment in INDEMNITY_PAYMENT_TYPES:
        return "indemnity"
    if payment in FIXED_PAYMENT_TYPES:
        return "fixed"
    if payment:
        return "unknown"

    category = (coverage_category or "").strip()
    if category in INDEMNITY_PAYMENT_TYPES:
        return "indemnity"
    if category in FIXED_PAYMENT_TYPES:
        return "fixed"
    if any(term in text for term in _NEGATED_INDEMNITY_TERMS):
        return "unknown"

    name = normalize_insurance_text(coverage_name)
    if any(term in name for term in _INDEMNITY_TERMS):
        return "indemnity"
    return "unknown"


def _coverage_domain(text: str) -> CoverageDomain:
    if _has_medical_term(text):
        return "medical_expense"
    if any(term in text for term in _LEGAL_COST_TERMS):
        return "legal_cost"
    if any(term in text for term in _LIABILITY_TERMS):
        return "liability"
    if any(term in text for term in _PROPERTY_TERMS):
        return "property_damage"
    if any(term in text for term in _DRIVER_TERMS):
        return "driver"
    if any(term in text for term in _TRAVEL_TERMS):
        return "travel"
    if text:
        return "other"
    return "unknown"


def _has_product_level_medical_indemnity(text: str) -> bool:
    return any(term in text for term in ("실손의료보험", "실손보험", "실비보험"))


def _has_medical_term(text: str) -> bool:
    return any(term in text for term in _MEDICAL_TERMS)


def _combined_text(*values: str | None) -> str:
    return normalize_insurance_text(" ".join(value for value in values if value))


def normalize_insurance_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()
