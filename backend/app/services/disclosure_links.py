"""Deterministic insurer disclosure/terms links (not RAG)."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

_DATA = Path(__file__).resolve().parent / "data" / "disclosure_links.json"

DisclosureKind = Literal["life", "non_life", "integrated"]


@dataclass(frozen=True)
class DisclosureLink:
    kind: DisclosureKind
    name: str
    url: str
    description: str


@lru_cache(maxsize=1)
def _directory() -> dict[str, Any]:
    result: dict[str, Any] = json.loads(_DATA.read_text(encoding="utf-8"))
    return result


def disclosure_links_for_insurer(insurer: str | None) -> tuple[DisclosureLink, ...]:
    """Return official disclosure links for a parsed insurer name.

    The registry intentionally starts with association disclosure portals. They
    are stable enough for deterministic guidance while company-specific product
    disclosure URLs are collected and verified separately.
    """
    kind = _infer_kind(insurer or "")
    links = [_parse_link(raw) for raw in _directory().get("association_links", [])]
    selected = [link for link in links if link.kind in {kind, "integrated"}]
    return tuple(selected)


def _infer_kind(insurer: str) -> DisclosureKind:
    compact = insurer.replace(" ", "")
    if "생명" in compact or "라이프" in compact:
        return "life"
    return "non_life"


def _parse_link(raw: dict[str, Any]) -> DisclosureLink:
    return DisclosureLink(
        kind=raw["kind"],
        name=raw["name"],
        url=raw["url"],
        description=raw["description"],
    )
