"""Canonical age-to-life-stage rule shared by coverage consumers."""

from app.modules.coverage.contracts import LifeStage

_ADULT_MIN_AGE = 19
_SENIOR_MIN_AGE = 65


def life_stage_for_age(age: int) -> LifeStage:
    if age < _ADULT_MIN_AGE:
        return "어린이"
    if age >= _SENIOR_MIN_AGE:
        return "시니어"
    return "성인"
