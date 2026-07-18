"""Validated response contracts backed by operational reference data."""

from typing import Literal

from pydantic import BaseModel, Field

SourceReliability = Literal[
    "official",
    "public_research",
    "industry",
    "large_private_analysis",
    "private_guidance",
]


class ReferenceSource(BaseModel):
    label: str
    url: str
    published_at: str
    reliability: SourceReliability
    caveat: str


class ClaimChannelLink(BaseModel):
    label: str
    url: str


class ClaimChannelInsurer(BaseModel):
    name: str
    customer_center: str | None = None
    note: str | None = None
    links: list[ClaimChannelLink] = Field(default_factory=list)


class ClaimChannelMedicalIndemnity(BaseModel):
    name: str
    description: str | None = None
    call_center: str | None = None
    links: list[ClaimChannelLink] = Field(default_factory=list)


class ClaimChannelBlock(BaseModel):
    insurers: list[ClaimChannelInsurer] = Field(default_factory=list)
    medical_indemnity: ClaimChannelMedicalIndemnity | None = None


PremiumBenchmarkSource = ReferenceSource


class PremiumBenchmark(BaseModel):
    age_band_label: str
    min_age: int
    max_age: int
    average_monthly_income: int
    suggested_min_ratio: float
    suggested_max_ratio: float
    suggested_min_premium: int
    suggested_max_premium: int
    income_source: PremiumBenchmarkSource
    guide_source: PremiumBenchmarkSource
