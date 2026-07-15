"""Death benefit guide lookup from database-owned reference data."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.modules.portfolio.schemas import ReferenceSource
from app.modules.reference_data import load_database_reference_data


@dataclass(frozen=True)
class DeathBenefitContext:
    has_dependent_family: bool = False
    has_minor_children: bool = False
    has_major_debt: bool = False


@dataclass(frozen=True)
class DeathBenefitGuide:
    situation: str
    amount_label: str
    min_amount: int
    max_amount: int
    reason: str
    sources: tuple[ReferenceSource, ...]


@lru_cache(maxsize=1)
def _guide_rows() -> tuple[tuple[DeathBenefitContext, DeathBenefitGuide], ...]:
    payload = load_database_reference_data(
        "death_benefit_guides",
        _validate_payload,
    )
    sources = _source_index(payload["sources"])

    rows: list[tuple[DeathBenefitContext, DeathBenefitGuide]] = []
    for guide in payload["guides"]:
        context = DeathBenefitContext(
            has_dependent_family=guide["has_dependent_family"],
            has_minor_children=guide["has_minor_children"],
            has_major_debt=guide["has_major_debt"],
        )
        rows.append(
            (
                context,
                DeathBenefitGuide(
                    situation=guide["situation"],
                    amount_label=guide["amount_label"],
                    min_amount=guide["min_amount"],
                    max_amount=guide["max_amount"],
                    reason=guide["reason"],
                    sources=tuple(
                        sources[_source_id(value, sources)] for value in guide["source_ids"]
                    ),
                ),
            )
        )
    return tuple(rows)


def death_benefit_guide(context: DeathBenefitContext | None) -> DeathBenefitGuide:
    effective_context = context or DeathBenefitContext()
    for row_context, guide in _guide_rows():
        if row_context == effective_context:
            return guide
    raise ValueError("death benefit guide context is missing")


def _validate_payload(payload: object) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise TypeError("death benefit payload must be an object")

    sources = payload["sources"]
    guides = payload["guides"]
    if not isinstance(sources, list) or not isinstance(guides, list):
        raise TypeError("death benefit sources and guides must be arrays")

    for source in sources:
        if not isinstance(source, dict):
            raise TypeError("death benefit source must be an object")
        _require_text(source, "id")
        ReferenceSource.model_validate(source)

    seen_contexts: set[DeathBenefitContext] = set()
    for guide in guides:
        if not isinstance(guide, dict):
            raise TypeError("death benefit guide must be an object")
        context = DeathBenefitContext(
            has_dependent_family=_require_bool(guide, "has_dependent_family"),
            has_minor_children=_require_bool(guide, "has_minor_children"),
            has_major_debt=_require_bool(guide, "has_major_debt"),
        )
        if context in seen_contexts:
            raise ValueError("death benefit guide context duplicated")
        seen_contexts.add(context)

        _require_text(guide, "situation")
        _require_text(guide, "amount_label")
        _require_text(guide, "reason")
        source_ids = guide["source_ids"]
        if not isinstance(source_ids, list) or not source_ids:
            raise TypeError("death benefit guide source_ids must be a non-empty array")
        min_amount = _require_non_negative_int(guide, "min_amount")
        max_amount = _require_non_negative_int(guide, "max_amount")
        if max_amount < min_amount:
            raise ValueError("death benefit max amount must be >= min amount")

    if len(seen_contexts) != 8:
        raise ValueError("death benefit guides must cover all checkbox combinations")

    return {"sources": sources, "guides": guides}


def _source_index(raw_sources: list[dict[str, Any]]) -> dict[str, ReferenceSource]:
    sources: dict[str, ReferenceSource] = {}
    for raw in raw_sources:
        source_id = _require_text(raw, "id")
        if source_id in sources:
            raise ValueError("death benefit source duplicated")
        sources[source_id] = ReferenceSource.model_validate(raw)
    return sources


def _source_id(value: object, sources: dict[str, ReferenceSource]) -> str:
    if not isinstance(value, str) or value not in sources:
        raise ValueError("death benefit guide source id is unknown")
    return value


def _require_text(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _require_bool(data: dict[str, Any], key: str) -> bool:
    value = data[key]
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean")
    return value


def _require_non_negative_int(data: dict[str, Any], key: str) -> int:
    value = data[key]
    if not isinstance(value, int) or value < 0:
        raise TypeError(f"{key} must be a non-negative integer")
    return value
