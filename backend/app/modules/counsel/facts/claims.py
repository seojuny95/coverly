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
    """Return verified claim channels for insurers matched by coverage names.

    With no coverage name to narrow by, every insurer on file is the answer:
    the user asked where to claim, and we know all of their insurers.
    """

    if not [name for name in coverage_names if name.strip()]:
        return ClaimChannelsResult(
            channels=_channels_for(_all_insurers(policies)),
            unmatched=[],
        )

    matches, unmatched = match_coverage_names(policies, coverage_names)
    insurers = [match.보험사 for match in matches if match.보험사]
    return ClaimChannelsResult(channels=_channels_for(insurers), unmatched=unmatched)


def _all_insurers(policies: list[PolicyInput]) -> list[str]:
    return [policy.기본정보.보험사 for policy in policies if policy.기본정보.보험사]


def _channels_for(insurers: list[str]) -> ClaimChannelBlock:
    return claim_channel_block(
        list(dict.fromkeys(insurers)),
        include_medical_indemnity_service=False,
    )
