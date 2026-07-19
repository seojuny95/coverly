"""Curated insurer claim-channel reference data and API projection.

Turns the user's insurers + whether they hold 실손의료보험 into a deterministic claim-
channel block so answers can point to the right place without an LLM inventing
URLs. Insurer names live only in the data file, never in this module.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, cast

from app.modules.reference_data.contracts import (
    ClaimChannelBlock,
    ClaimChannelInsurer,
    ClaimChannelLink,
    ClaimChannelMedicalIndemnity,
)
from app.modules.reference_data.insurers import canonical_insurer_name
from app.modules.reference_data.loader import load_database_reference_data


@dataclass(frozen=True)
class ChannelLink:
    label: str
    url: str


@dataclass(frozen=True)
class InsurerChannel:
    name: str
    customer_center: str | None
    homepage: str | None
    claim_link: str | None
    app: str | None
    note: str | None


@dataclass(frozen=True)
class MedicalIndemnityService:
    name: str
    description: str | None
    call_center: str | None
    links: tuple[ChannelLink, ...]


@dataclass(frozen=True)
class ClaimChannelSet:
    insurers: tuple[InsurerChannel, ...]
    medical_indemnity: MedicalIndemnityService | None


@lru_cache(maxsize=1)
def _directory() -> dict[str, Any]:
    return load_database_reference_data(
        "claim_channels",
        _validate_directory,
    )


def _validate_directory(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("보험사"), list):
        raise ValueError("claim channels must contain an insurer list")
    return cast(dict[str, Any], value)


def _match(insurer: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    name = insurer.strip()
    if not name:
        return None
    canonical_name = canonical_insurer_name(name)
    if canonical_name is None:
        return None
    for entry in entries:
        if canonical_insurer_name(entry["보험사"]) == canonical_name:
            return entry
    return None


def _medical_indemnity_service(directory: dict[str, Any]) -> MedicalIndemnityService:
    block = directory["실손의료보험"]
    links = tuple(
        ChannelLink(label=channel["이름"], url=channel["링크"])
        for channel in block.get("채널", [])
        if channel.get("링크")
    )
    return MedicalIndemnityService(
        name=block["이름"],
        description=block.get("설명"),
        call_center=block.get("콜센터"),
        links=links,
    )


def channels_for(
    insurers: list[str],
    *,
    has_medical_indemnity: bool,
) -> ClaimChannelSet:
    """Deterministic claim-channel block for the user's insurers.

    `has_medical_indemnity` includes the 실손24 medical-expense claim service.
    Unknown insurers are skipped; duplicates collapse to one entry.
    """

    directory = _directory()
    matched: list[InsurerChannel] = []
    seen: set[str] = set()
    for insurer in insurers:
        entry = _match(insurer, directory["보험사"])
        if entry is None or entry["보험사"] in seen:
            continue
        seen.add(entry["보험사"])
        matched.append(
            InsurerChannel(
                name=entry["보험사"],
                customer_center=entry.get("고객센터"),
                homepage=entry.get("홈페이지"),
                claim_link=entry.get("청구링크"),
                app=entry.get("앱"),
                note=entry.get("비고"),
            )
        )

    medical_indemnity = _medical_indemnity_service(directory) if has_medical_indemnity else None
    return ClaimChannelSet(
        insurers=tuple(matched),
        medical_indemnity=medical_indemnity,
    )


def claim_channel_block(
    insurers: list[str],
    *,
    has_medical_indemnity: bool,
) -> ClaimChannelBlock:
    """API-shaped claim channels (with clickable links) for the given insurers."""

    channel_set = channels_for(
        insurers,
        has_medical_indemnity=has_medical_indemnity,
    )
    schema_insurers: list[ClaimChannelInsurer] = []
    for insurer in channel_set.insurers:
        links: list[ClaimChannelLink] = []
        if insurer.claim_link:
            links.append(ClaimChannelLink(label="청구 링크", url=insurer.claim_link))
        if insurer.homepage and insurer.homepage != insurer.claim_link:
            links.append(ClaimChannelLink(label="홈페이지", url=insurer.homepage))
        schema_insurers.append(
            ClaimChannelInsurer(
                name=insurer.name,
                customer_center=insurer.customer_center,
                note=insurer.note,
                links=links,
            )
        )

    medical_indemnity: ClaimChannelMedicalIndemnity | None = None
    if channel_set.medical_indemnity is not None:
        source = channel_set.medical_indemnity
        medical_indemnity = ClaimChannelMedicalIndemnity(
            name=source.name,
            description=source.description,
            call_center=source.call_center,
            links=[ClaimChannelLink(label=link.label, url=link.url) for link in source.links],
        )
    return ClaimChannelBlock(
        insurers=schema_insurers,
        medical_indemnity=medical_indemnity,
    )
