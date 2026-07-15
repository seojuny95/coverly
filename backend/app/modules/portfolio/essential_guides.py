"""Supabase-owned guide amounts and sources for essential coverage checks."""

from dataclasses import dataclass
from functools import lru_cache

from app.modules.portfolio.schemas import EssentialCoverageKind, ReferenceSource
from app.modules.reference_data import load_database_reference_data


@dataclass(frozen=True)
class EssentialCoverageGuide:
    kind: EssentialCoverageKind
    reference_min_amount: int | None
    reference_max_amount: int | None
    basis: str | None
    sources: tuple[ReferenceSource, ...]


@lru_cache(maxsize=1)
def essential_coverage_guides() -> dict[EssentialCoverageKind, EssentialCoverageGuide]:
    return load_database_reference_data(
        "essential_coverage_guides",
        _validate_essential_coverage_guides,
    )


def _validate_essential_coverage_guides(
    payload: object,
) -> dict[EssentialCoverageKind, EssentialCoverageGuide]:
    if not isinstance(payload, dict):
        raise ValueError("essential coverage guides must be an object")

    raw_sources = payload.get("sources")
    raw_items = payload.get("items")
    if not isinstance(raw_sources, list) or not isinstance(raw_items, list):
        raise ValueError("essential coverage guides must contain sources and items")

    sources = _source_index(raw_sources)
    guides: dict[EssentialCoverageKind, EssentialCoverageGuide] = {}
    for item in raw_items:
        guide = _guide_from_item(item, sources)
        if guide.kind in guides:
            raise ValueError(f"duplicate essential coverage guide: {guide.kind}")
        guides[guide.kind] = guide

    required: set[EssentialCoverageKind] = {
        "death",
        "cancer",
        "cerebrovascular",
        "ischemic_heart",
        "indemnity",
    }
    if set(guides) != required:
        raise ValueError("essential coverage guides must cover every essential kind")
    return guides


def _source_index(raw_sources: list[object]) -> dict[str, ReferenceSource]:
    sources: dict[str, ReferenceSource] = {}
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise ValueError("essential coverage guide sources must be objects")
        source_id = raw.get("id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("essential coverage guide sources must have ids")
        source = ReferenceSource.model_validate(raw)
        if source_id in sources:
            raise ValueError(f"duplicate essential coverage guide source: {source_id}")
        sources[source_id] = source
    return sources


def _guide_from_item(
    raw: object,
    sources: dict[str, ReferenceSource],
) -> EssentialCoverageGuide:
    if not isinstance(raw, dict):
        raise ValueError("essential coverage guide items must be objects")

    kind = _kind(raw.get("kind"))
    min_amount = _optional_amount(raw.get("reference_min_amount"))
    max_amount = _optional_amount(raw.get("reference_max_amount"))
    if (min_amount is None) != (max_amount is None):
        raise ValueError("essential coverage guide amount range must be complete")
    if min_amount is not None and max_amount is not None and max_amount < min_amount:
        raise ValueError("essential coverage guide max amount must be >= min amount")

    source_ids = raw.get("source_ids")
    if not isinstance(source_ids, list):
        raise ValueError("essential coverage guide items must contain source_ids")
    item_sources = tuple(sources[_source_id(value, sources)] for value in source_ids)

    basis = raw.get("basis")
    if basis is not None and not isinstance(basis, str):
        raise ValueError("essential coverage guide basis must be a string")

    return EssentialCoverageGuide(
        kind=kind,
        reference_min_amount=min_amount,
        reference_max_amount=max_amount,
        basis=basis.strip() if isinstance(basis, str) and basis.strip() else None,
        sources=item_sources,
    )


def _kind(value: object) -> EssentialCoverageKind:
    allowed: set[EssentialCoverageKind] = {
        "death",
        "cancer",
        "cerebrovascular",
        "ischemic_heart",
        "indemnity",
    }
    if value not in allowed:
        raise ValueError("unknown essential coverage guide kind")
    return value


def _optional_amount(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("essential coverage guide amount must be a non-negative integer")
    return value


def _source_id(value: object, sources: dict[str, ReferenceSource]) -> str:
    if not isinstance(value, str) or value not in sources:
        raise ValueError("essential coverage guide source id is unknown")
    return value
