"""Derive insured demographics from a policy without exposing raw identifiers.

Resident-registration numbers are used only as a local parsing signal. The
birthdate and identifier are discarded immediately; callers receive only the
completed age, gender, and life stage needed by the analysis experience.
"""

import re
from datetime import date
from typing import cast

from app.core.pii import (
    MASKED_RESIDENT_IDENTIFIER,
    iter_resident_identifier_matches,
    mask_resident_identifiers,
)
from app.modules.coverage.life_stage import life_stage_for_age
from app.modules.policy.models import InsuredDemographics, InsuredGender

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
_EXPLICIT_AGE_PATTERN = re.compile(r"(?:만\s*)?(?P<age>\d{1,3})\s*세")
_EXPLICIT_GENDER_PATTERN = re.compile(r"(?<![가-힣])(?P<gender>남성|여성)(?![가-힣])")


def mask_demographic_identifiers(text: str) -> str:
    """Mask RRN-like values before text crosses an external model boundary.

    Masking is deliberately shape-based rather than validity-based. Even an
    identifier with an unsupported century digit or a mistyped date remains
    sensitive and must not be sent to an LLM unchanged.
    """
    return mask_resident_identifiers(text, replacement=MASKED_RESIDENT_IDENTIFIER)


def extract_insured_demographics(
    text: str,
    *,
    today: date | None = None,
) -> InsuredDemographics | None:
    """Return safe insured demographics explicitly stated for the insured.

    When both policy-holder and insured identifiers exist, a candidate after
    the most recent ``피보험자`` label is preferred. If the text contains no
    identity labels at all, the first valid identifier is used as a fallback
    for simple one-person policy layouts. A line that explicitly states both
    the insured's age and gender is accepted without retaining identifiers.
    """
    candidates = list(iter_resident_identifier_matches(text))
    if candidates:
        insured_candidates = [
            candidate for candidate in candidates if _belongs_to_insured(text, candidate.start())
        ]
        if insured_candidates:
            candidates = insured_candidates
        elif "피보험자" in text or "계약자" in text:
            candidates = []

        reference_date = today or date.today()
        for candidate in candidates:
            demographics = _safe_demographics(candidate, reference_date)
            if demographics is not None:
                return demographics

    return _explicit_insured_demographics(text)


def _explicit_insured_demographics(text: str) -> InsuredDemographics | None:
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        if "피보험자" not in line:
            continue

        age_match = _EXPLICIT_AGE_PATTERN.search(line)
        gender_match = _EXPLICIT_GENDER_PATTERN.search(line)
        if age_match is None or gender_match is None:
            continue

        age = int(age_match.group("age"))
        if not 0 <= age <= 120:
            continue
        gender = cast(InsuredGender, gender_match.group("gender"))
        return {
            "나이": age,
            "성별": gender,
            "생애단계": life_stage_for_age(age),
        }

    return None


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
        "생애단계": life_stage_for_age(age),
    }


def _completed_age(birth_date: date, reference_date: date) -> int:
    birthday_has_passed = (reference_date.month, reference_date.day) >= (
        birth_date.month,
        birth_date.day,
    )
    return reference_date.year - birth_date.year - (not birthday_has_passed)
