"""Shared contracts for portfolio consultation features."""

from typing import Literal

from pydantic import BaseModel

from app.modules.consultation.contracts import (
    ConsultationEvidence,
    DemographicSource,
    DemographicStatus,
    Gender,
    InsuredDemographics,
)

GuidanceBasis = Literal["confirmed_fact", "general_guidance"]

__all__ = [
    "AnswerSection",
    "ConsultationEvidence",
    "DemographicSource",
    "DemographicStatus",
    "Gender",
    "GuidanceBasis",
    "InsuredDemographics",
]


class AnswerSection(BaseModel):
    title: str
    content: str
    basis: GuidanceBasis
