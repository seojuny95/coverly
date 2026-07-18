"""Shared coverage-domain contracts."""

from typing import Literal

CoverageDomain = Literal[
    "medical_expense",
    "travel_medical_expense",
    "legal_cost",
    "property_damage",
    "liability",
    "auto",
    "other",
]
