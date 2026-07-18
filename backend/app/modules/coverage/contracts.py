"""Shared coverage-domain contracts."""

from typing import Literal

CoverageType = Literal["담보", "부가"]
InsuredGender = Literal["남성", "여성"]
LifeStage = Literal["어린이", "성인", "시니어"]
CoverageDomain = Literal[
    "medical_expense",
    "travel_medical_expense",
    "legal_cost",
    "property_damage",
    "liability",
    "auto",
    "other",
]
