"""Compatibility imports for claim-channel reference data."""

from app.modules.reference_data.claim_channels import (
    ChannelLink,
    ClaimChannelSet,
    InsurerChannel,
    MedicalIndemnityService,
    _directory,
    channels_for,
    claim_channel_block,
)

__all__ = [
    "ChannelLink",
    "ClaimChannelSet",
    "InsurerChannel",
    "MedicalIndemnityService",
    "_directory",
    "channels_for",
    "claim_channel_block",
]
