from typing import get_args

from app.core.generation import GenerationMode
from app.modules.coverage.contracts import CoverageDomain
from app.modules.policy.models import CoverageType, InsuredGender, LifeStage
from app.modules.portfolio.schemas import (
    ActualLossCoverageDomain,
    ClaimChannelBlock,
    CoverageInput,
    PolicyInsuredDemographicsInput,
    PortfolioCoverageSummary,
    PremiumBenchmarkSource,
    ReferenceSource,
)


def test_claim_channel_and_reference_models_have_single_runtime_identity() -> None:
    claim_channel_types = get_args(
        PortfolioCoverageSummary.model_fields["claim_channels"].annotation
    )
    assert ClaimChannelBlock in claim_channel_types
    assert PremiumBenchmarkSource is ReferenceSource


def test_api_models_use_shared_literal_contracts() -> None:
    assert ActualLossCoverageDomain is CoverageDomain
    assert CoverageType in get_args(CoverageInput.model_fields["유형"].annotation)
    assert set(get_args(PolicyInsuredDemographicsInput.model_fields["성별"].annotation)) == set(
        get_args(InsuredGender)
    )
    assert set(get_args(PolicyInsuredDemographicsInput.model_fields["생애단계"].annotation)) == set(
        get_args(LifeStage)
    )
    assert set(get_args(GenerationMode)) == {"llm", "fallback"}
