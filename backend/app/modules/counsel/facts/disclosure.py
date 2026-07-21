"""Deterministic official disclosure/terms link facts for counsel."""

from pydantic import BaseModel, Field

from app.modules.coverage.disclosure_links import (
    DisclosureKind,
    DisclosureLink,
    disclosure_links_for_insurer,
)
from app.modules.portfolio.schemas import PolicyInput


class DisclosureLinkInfo(BaseModel):
    kind: DisclosureKind
    name: str
    url: str
    description: str


class InsurerDisclosureLinks(BaseModel):
    보험사: str
    links: list[DisclosureLinkInfo] = Field(default_factory=list)


class DisclosureLinksResult(BaseModel):
    insurers: list[InsurerDisclosureLinks] = Field(default_factory=list)


def get_disclosure_link_facts(policies: list[PolicyInput]) -> DisclosureLinksResult:
    """Return official disclosure portal links grouped by insurer actually on file.

    Only insurers with a name recorded on a policy are looked up -- nothing is
    guessed. An insurer whose kind (life/non-life) has no configured link
    yields an empty `links` list rather than an error, so a caller can safely
    iterate the result even when the registry has nothing to say yet.
    """

    return DisclosureLinksResult(
        insurers=[
            InsurerDisclosureLinks(
                보험사=insurer,
                links=[_link_info(link) for link in disclosure_links_for_insurer(insurer)],
            )
            for insurer in _distinct_insurers(policies)
        ]
    )


def _distinct_insurers(policies: list[PolicyInput]) -> list[str]:
    insurers = [policy.기본정보.보험사 for policy in policies if policy.기본정보.보험사]
    return list(dict.fromkeys(insurers))


def _link_info(link: DisclosureLink) -> DisclosureLinkInfo:
    return DisclosureLinkInfo(
        kind=link.kind,
        name=link.name,
        url=link.url,
        description=link.description,
    )
