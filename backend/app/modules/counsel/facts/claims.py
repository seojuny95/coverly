"""Deterministic claim-channel facts for counsel."""

from pydantic import BaseModel

from app.modules.counsel.facts.coverages import UnmatchedCoverageName, match_coverage_names
from app.modules.portfolio.schemas import PolicyInput
from app.modules.reference_data.claim_channels import claim_channel_block
from app.modules.reference_data.contracts import ClaimChannelBlock


class ClaimChannelsResult(BaseModel):
    channels: ClaimChannelBlock
    unmatched: list[UnmatchedCoverageName]


def get_claim_channel_facts(
    policies: list[PolicyInput],
    coverage_names: list[str],
) -> ClaimChannelsResult:
    """Return verified claim channels for insurers matched by coverage names."""

    matches, unmatched = match_coverage_names(policies, coverage_names)
    insurers = [match.보험사 for match in matches if match.보험사]
    channels = claim_channel_block(
        list(dict.fromkeys(insurers)),
        include_medical_indemnity_service=False,
    )
    return ClaimChannelsResult(channels=channels, unmatched=unmatched)
