"""Deterministic coverage taxonomy for informational life-stage checks.

The checklist is a product heuristic, not an official adequacy standard. It
must not be used to recommend products or assert that an amount is sufficient.
"""

import re
from dataclasses import dataclass

from app.modules.coverage.indemnity import is_medical_indemnity_name
from app.modules.coverage.life_stage import life_stage_for_age as life_stage_for

CANCER = "암 진단"
CEREBRO = "뇌혈관 진단"
HEART = "심장질환 진단"
INJURY_DISABILITY = "상해 후유장해"
DISEASE_DISABILITY = "질병 후유장해"
HOSPITAL = "입원"
SURGERY = "수술"
DEATH = "사망"
MEDICAL_INDEMNITY = "실손의료비"
CARE = "간병"

_LIFE_STAGE_ESSENTIALS = {
    "어린이": (MEDICAL_INDEMNITY, DISEASE_DISABILITY, SURGERY, HOSPITAL, CANCER),
    "성인": (CANCER, CEREBRO, HEART, MEDICAL_INDEMNITY, DEATH, INJURY_DISABILITY),
    "시니어": (CANCER, CEREBRO, HEART, MEDICAL_INDEMNITY, CARE),
}


@dataclass(frozen=True)
class LifeStageCheck:
    life_stage: str
    held: tuple[str, ...]
    missing: tuple[str, ...]


def classify_coverage(name: str) -> str | None:
    normalized = re.sub(r"\s+", "", name)
    if is_medical_indemnity_name(normalized):
        return MEDICAL_INDEMNITY
    if "상해" in normalized and "후유장해" in normalized:
        return INJURY_DISABILITY
    if "질병" in normalized and "후유장해" in normalized:
        return DISEASE_DISABILITY
    if "입원" in normalized:
        return HOSPITAL
    if "수술" in normalized:
        return SURGERY
    if "간병" in normalized or "요양" in normalized:
        return CARE
    if "사망" in normalized:
        return DEATH
    if "암진단" in normalized or "악성신생물" in normalized:
        return CANCER
    if any(term in normalized for term in ("뇌혈관", "뇌졸중", "뇌출혈", "뇌경색")):
        return CEREBRO
    if any(term in normalized for term in ("허혈성심", "심근경색", "심장질환")):
        return HEART
    return None


def check_life_stage(age: int, coverage_names: list[str]) -> LifeStageCheck:
    life_stage = life_stage_for(age)
    held_categories = {classify_coverage(name) for name in coverage_names}
    essentials = _LIFE_STAGE_ESSENTIALS[life_stage]
    held = tuple(item for item in essentials if item in held_categories)
    missing = tuple(item for item in essentials if item not in held_categories)
    return LifeStageCheck(life_stage=life_stage, held=held, missing=missing)
