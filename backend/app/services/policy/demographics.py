"""Derive insured demographics from a policy without exposing raw identifiers.

Resident-registration numbers are used only as a local parsing signal. The
birthdate and identifier are discarded immediately; callers receive only the
completed age, gender, and life stage needed by the analysis experience.
"""

import re
from collections.abc import Iterator
from datetime import date

from app.services.policy.models import InsuredDemographics, InsuredGender, LifeStage

_MASKED_IDENTIFIER = "******-*******"

# A formatted value may have a hyphen or extracted whitespace between the
# birthdate and the century/gender digit. The compact shape is accepted only
# when all thirteen positions are present, which avoids treating an arbitrary
# seven-digit policy value as an identifier.
_FORMATTED_IDENTIFIER = re.compile(
    r"(?<!\d)"
    r"(?P<birth>\d{6})"
    r"(?:\s*-\s*|\s+)"
    r"(?P<code>\d)"
    r"(?P<tail>[\d*]{0,6})"
    r"(?![\d*])"
)
_COMPACT_IDENTIFIER = re.compile(
    r"(?<!\d)"
    r"(?P<birth>\d{6})"
    r"(?P<code>\d)"
    r"(?P<tail>[\d*]{6})"
    r"(?![\d*])"
)
_IDENTIFIER_PATTERNS = (_FORMATTED_IDENTIFIER, _COMPACT_IDENTIFIER)

_CENTURY_AND_GENDER: dict[str, tuple[int, InsuredGender]] = {
    "1": (1900, "남성"),
    "2": (1900, "여성"),
    "3": (2000, "남성"),
    "4": (2000, "여성"),
    "5": (1900, "남성"),
    "6": (1900, "여성"),
    "7": (2000, "남성"),
    "8": (2000, "여성"),
}


def mask_demographic_identifiers(text: str) -> str:
    """Mask RRN-like values before text crosses an external model boundary.

    Masking is deliberately shape-based rather than validity-based. Even an
    identifier with an unsupported century digit or a mistyped date remains
    sensitive and must not be sent to an LLM unchanged.
    """
    masked = text
    for pattern in _IDENTIFIER_PATTERNS:
        masked = pattern.sub(_MASKED_IDENTIFIER, masked)
    return masked


def extract_insured_demographics(
    text: str,
    *,
    today: date | None = None,
) -> InsuredDemographics | None:
    """Return safe insured demographics from the first valid insured ID.

    When both policy-holder and insured identifiers exist, a candidate after
    the most recent ``피보험자`` label is preferred. If the text contains no
    identity labels at all, the first valid identifier is used as a safe
    fallback for simple one-person policy layouts.
    """
    candidates = list(_iter_identifier_matches(text))
    if not candidates:
        return None

    insured_candidates = [
        candidate for candidate in candidates if _belongs_to_insured(text, candidate.start())
    ]
    if insured_candidates:
        candidates = insured_candidates
    elif "피보험자" in text or "계약자" in text:
        return None

    reference_date = today or date.today()
    for candidate in candidates:
        demographics = _safe_demographics(candidate, reference_date)
        if demographics is not None:
            return demographics
    return None


def _iter_identifier_matches(text: str) -> Iterator[re.Match[str]]:
    matches = [match for pattern in _IDENTIFIER_PATTERNS for match in pattern.finditer(text)]
    matches.sort(key=lambda match: match.start())
    yield from matches


def _belongs_to_insured(text: str, candidate_start: int) -> bool:
    prefix = text[:candidate_start]
    last_insured_label = prefix.rfind("피보험자")
    last_policy_holder_label = prefix.rfind("계약자")
    return last_insured_label >= 0 and last_insured_label > last_policy_holder_label


def _safe_demographics(
    candidate: re.Match[str],
    reference_date: date,
) -> InsuredDemographics | None:
    century_and_gender = _CENTURY_AND_GENDER.get(candidate.group("code"))
    if century_and_gender is None:
        return None

    birth_digits = candidate.group("birth")
    century, gender = century_and_gender
    birth_year = century + int(birth_digits[:2])

    try:
        birth_date = date(
            birth_year,
            int(birth_digits[2:4]),
            int(birth_digits[4:6]),
        )
    except ValueError:
        return None

    age = _completed_age(birth_date, reference_date)
    if not 0 <= age <= 120:
        return None

    return {
        "나이": age,
        "성별": gender,
        "생애단계": _life_stage(age),
    }


def _completed_age(birth_date: date, reference_date: date) -> int:
    birthday_has_passed = (reference_date.month, reference_date.day) >= (
        birth_date.month,
        birth_date.day,
    )
    return reference_date.year - birth_date.year - (not birthday_has_passed)


def _life_stage(age: int) -> LifeStage:
    if age < 19:
        return "어린이"
    if age >= 65:
        return "시니어"
    return "성인"
