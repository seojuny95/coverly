"""Deterministic indemnity classification helpers.

Korean insurance copy uses "실손" both for medical indemnity insurance and for
generic actual-loss reimbursement. This module keeps those concepts separate.
"""

import re
from dataclasses import dataclass
from typing import Literal, Protocol

from app.modules.coverage.contracts import CoverageDomain

PaymentBasis = Literal["fixed", "indemnity", "unknown"]
MedicalIndemnityStatus = Literal["confirmed", "excluded", "unknown"]


class CoverageContext(Protocol):
    @property
    def 담보명(self) -> str: ...

    @property
    def 보장분류(self) -> str | None: ...

    @property
    def 지급유형(self) -> str | None: ...

    @property
    def 보장내용(self) -> str | None: ...

    @property
    def 해설(self) -> str | None: ...


class PolicyInfoContext(Protocol):
    @property
    def 보험분류(self) -> str | None: ...

    @property
    def 상품명(self) -> str | None: ...

    @property
    def 상품태그(self) -> list[str]: ...


class PolicyContext(Protocol):
    @property
    def 기본정보(self) -> PolicyInfoContext: ...


@dataclass(frozen=True)
class IndemnityClassification:
    payment_basis: PaymentBasis
    coverage_domain: CoverageDomain
    medical_indemnity_status: MedicalIndemnityStatus


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()


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
_NORMALIZED_FIXED_PAYMENT_TYPES = frozenset(_normalize(item) for item in _FIXED_PAYMENT_TYPES)
_NORMALIZED_INDEMNITY_PAYMENT_TYPES = frozenset(
    _normalize(item) for item in _INDEMNITY_PAYMENT_TYPES
)
_NORMALIZED_INDEMNITY_CATEGORIES = frozenset(_normalize(item) for item in _INDEMNITY_CATEGORIES)
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
    "질병치료비",
    "상해치료비",
    "상해실비",
    "질병실비",
    "상해실손",
    "질병실손",
)
_TRAVEL_MEDICAL_TERMS = ("해외의료비", "해외실손의료비", "국외의료비")
_TRAVEL_POLICY_TERMS = ("여행자보험", "여행보험", "해외여행")
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
_DAMAGE_CLASSIFICATIONS = frozenset(
    {
        "손해보험",
        "자동차",
        "자동차보험",
        "운전자",
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


def classify_indemnity(
    coverage: CoverageContext,
    *,
    policy: PolicyContext | None = None,
) -> IndemnityClassification:
    """Classify actual-loss reimbursement separately from medical indemnity."""

    text = _coverage_text(coverage)
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


def has_negated_actual_loss_marker(coverage: CoverageContext) -> bool:
    """Return whether coverage metadata explicitly denies actual-loss payment."""

    normalized_name = _normalize(coverage.담보명)
    normalized_category = _normalize(coverage.보장분류 or "")
    return any(
        pattern in normalized_name or pattern in normalized_category
        for pattern in _NEGATED_INDEMNITY_PATTERNS
    )


def _payment_basis(coverage: CoverageContext) -> PaymentBasis:
    payment_type = (coverage.지급유형 or "").strip()
    normalized_payment_type = _normalize(payment_type)
    if normalized_payment_type in _NORMALIZED_INDEMNITY_PAYMENT_TYPES:
        return "indemnity"
    if normalized_payment_type in _NORMALIZED_FIXED_PAYMENT_TYPES:
        return "fixed"
    if payment_type:
        return "unknown"

    coverage_category = (coverage.보장분류 or "").strip()
    normalized_name = _normalize(coverage.담보명)
    normalized_category = _normalize(coverage_category)
    if has_negated_actual_loss_marker(coverage):
        return "unknown"
    if normalized_category in _NORMALIZED_INDEMNITY_CATEGORIES:
        return "indemnity"
    if _contains_any(normalized_name, _INDEMNITY_NAME_TERMS):
        return "indemnity"
    return "unknown"


def _coverage_domain(text: str, policy: PolicyContext | None) -> CoverageDomain:
    if _is_travel_policy_context(policy) and _contains_any(text, _MEDICAL_TERMS):
        return "travel_medical_expense"
    if _is_auto_policy_context(policy):
        return "auto"
    for domain, terms in _domain_priorities(policy):
        if _contains_any(text, terms):
            return domain
    return _policy_default_domain(policy)


def _domain_priorities(
    policy: PolicyContext | None,
) -> tuple[tuple[CoverageDomain, tuple[str, ...]], ...]:
    if is_damage_policy_context(policy):
        return (
            ("auto", _AUTO_TERMS),
            ("legal_cost", _LEGAL_TERMS),
            ("liability", _LIABILITY_TERMS),
            ("property_damage", _PROPERTY_TERMS),
            ("travel_medical_expense", _TRAVEL_MEDICAL_TERMS),
            ("medical_expense", _MEDICAL_TERMS),
        )
    return (
        ("legal_cost", _LEGAL_TERMS),
        ("liability", _LIABILITY_TERMS),
        ("auto", _AUTO_TERMS),
        ("property_damage", _PROPERTY_TERMS),
        ("travel_medical_expense", _TRAVEL_MEDICAL_TERMS),
        ("medical_expense", _MEDICAL_TERMS),
    )


def _coverage_text(coverage: CoverageContext) -> str:
    return _normalize(
        " ".join(
            [
                coverage.담보명,
                coverage.보장분류 or "",
                coverage.지급유형 or "",
                coverage.보장내용 or "",
                coverage.해설 or "",
            ]
        )
    )


def _policy_default_domain(policy: PolicyContext | None) -> CoverageDomain:
    if policy is None or _is_travel_policy_context(policy):
        return "other"

    identity = _policy_identity(policy)
    for domain, terms in _domain_priorities(policy):
        if domain != "travel_medical_expense" and _contains_any(identity, terms):
            return domain
    return "other"


def is_damage_policy_context(policy: PolicyContext | None) -> bool:
    """Return whether policy belongs to the separately handled damage branch."""

    if policy is None:
        return False
    category = policy.기본정보.보험분류 or ""
    tags = policy.기본정보.상품태그
    return category in _DAMAGE_CLASSIFICATIONS or any(tag in _DAMAGE_TAG_TERMS for tag in tags)


def _is_travel_policy_context(policy: PolicyContext | None) -> bool:
    if policy is None:
        return False
    return _contains_any(_policy_identity(policy), _TRAVEL_POLICY_TERMS)


def _is_auto_policy_context(policy: PolicyContext | None) -> bool:
    if policy is None:
        return False
    return _contains_any(_policy_identity(policy), _AUTO_TERMS)


def _policy_identity(policy: PolicyContext) -> str:
    return _normalize(
        " ".join(
            [
                policy.기본정보.보험분류 or "",
                policy.기본정보.상품명 or "",
                *policy.기본정보.상품태그,
            ]
        )
    )


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_normalize(term) in text for term in terms)
