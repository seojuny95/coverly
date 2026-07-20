"""Deterministic claim-channel facts for counsel."""

from pydantic import BaseModel

from app.modules.counsel.facts.coverages import UnmatchedCoverageName, match_coverage_names
from app.modules.coverage.indemnity import is_medical_indemnity_name
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
    """Return verified claim channels for the coverages in question.

    With no coverage name to narrow by, every insurer on file is the answer:
    the user asked where to claim, and we know all of their insurers.
    """

    requested = [name for name in coverage_names if name.strip()]
    if not requested:
        return ClaimChannelsResult(
            channels=_channels_for(_all_insurers(policies), _all_coverage_names(policies)),
            unmatched=[],
        )

    matches, unmatched = match_coverage_names(policies, requested)
    insurers = [match.보험사 for match in matches if match.보험사]
    matched_names = [match.담보명 for match in matches]
    return ClaimChannelsResult(
        channels=_channels_for(insurers, matched_names),
        unmatched=unmatched,
    )


def _all_insurers(policies: list[PolicyInput]) -> list[str]:
    return [policy.기본정보.보험사 for policy in policies if policy.기본정보.보험사]


def _all_coverage_names(policies: list[PolicyInput]) -> list[str]:
    return [coverage.담보명 for policy in policies for coverage in policy.보장목록]


def _channels_for(insurers: list[str], coverage_names: list[str]) -> ClaimChannelBlock:
    """Attach the 실손24 resource only when a 실손 coverage is actually in play."""

    return claim_channel_block(
        list(dict.fromkeys(insurers)),
        include_medical_indemnity_service=any(
            is_medical_indemnity_name(name) for name in coverage_names
        ),
    )
