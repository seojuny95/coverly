"""Validated, versioned fixture for the public sample portfolio."""

from functools import lru_cache
from pathlib import Path
from typing import Final, Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.modules.policy.schemas import PolicyParseResponse
from app.modules.portfolio.schemas import (
    DeathBenefitGuideInput,
    PortfolioCoverageSummary,
)
from app.rag.policy.models import PolicyContentType

SAMPLE_FIXTURE_SCHEMA_VERSION: Final[Literal[1]] = 1
SAMPLE_PORTFOLIO_VERSION: Final[Literal[1]] = 1
SAMPLE_GENERATOR_VERSION: Final[Literal["2026-08-14.1"]] = "2026-08-14.1"
_FIXTURE_PATH = Path(__file__).with_name("sample-portfolio.json")


class SampleRagChunk(BaseModel):
    text: str = Field(min_length=1)
    content_type: PolicyContentType
    table_index: int | None = None
    embedding: list[float] = Field(min_length=1)


class SamplePolicyFixture(BaseModel):
    file_name: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result: PolicyParseResponse
    rag_chunks: list[SampleRagChunk] = Field(min_length=1)


class SampleAnalysisFixture(BaseModel):
    death_benefit_context: DeathBenefitGuideInput
    result: PortfolioCoverageSummary


class SamplePortfolioFixture(BaseModel):
    schema_version: Literal[1]
    portfolio_version: Literal[1]
    generator_version: Literal["2026-08-14.1"]
    embedding_model: str = Field(min_length=1)
    embedding_dimensions: int = Field(gt=0)
    policies: list[SamplePolicyFixture] = Field(min_length=4, max_length=4)
    analyses: list[SampleAnalysisFixture] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_fixture_consistency(self) -> Self:
        document_ids = [policy.result.document_id for policy in self.policies]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("Sample policy document ids must be unique")
        if any(
            len(chunk.embedding) != self.embedding_dimensions
            for policy in self.policies
            for chunk in policy.rag_chunks
        ):
            raise ValueError("Sample embedding dimensions are inconsistent")

        contexts = {
            (
                analysis.death_benefit_context.has_dependent_family,
                analysis.death_benefit_context.has_minor_children,
                analysis.death_benefit_context.has_major_debt,
            )
            for analysis in self.analyses
        }
        if contexts != {
            (False, False, False),
            (True, False, False),
            (False, True, False),
            (False, False, True),
        }:
            raise ValueError("Sample analysis contexts are incomplete")
        return self


@lru_cache(maxsize=1)
def load_sample_portfolio_fixture() -> SamplePortfolioFixture:
    return SamplePortfolioFixture.model_validate_json(_FIXTURE_PATH.read_text(encoding="utf-8"))
