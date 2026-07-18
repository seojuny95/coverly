"""Structured evidence selectors for QA agent tools."""

from app.modules.coverage.matching import canonicalize_coverage_name
from app.modules.qa.context import QaContext
from app.modules.qa.contracts import ConsultationEvidence


def coverage_evidence_by_names(
    context: QaContext,
    names: list[str],
    *,
    max_items: int = 24,
) -> tuple[ConsultationEvidence, ...]:
    """Match model-supplied entities against actual uploaded-data identities."""

    requested = {canonicalize_coverage_name(name).normalized_key for name in names if name.strip()}
    if not requested:
        return ()

    matched: list[ConsultationEvidence] = []
    for item in context.catalog.items:
        identities = _evidence_identities(item)
        if requested.isdisjoint(identities):
            continue
        matched.append(item)
        if len(matched) == max_items:
            break
    return tuple(matched)


def overlap_evidence(context: QaContext) -> tuple[ConsultationEvidence, ...]:
    """Select overlap facts from structured aggregation flags, not question text."""

    duplicate_fixed = {
        item.normalized_name
        for item in context.facts.coverage_summary.totals
        if len(item.composition) > 1
    }
    duplicate_actual_loss = {
        (item.policy_id, item.normalized_name)
        for item in context.facts.coverage_summary.actual_loss_coverages
        if item.duplicate_across_contracts
    }

    matched: list[ConsultationEvidence] = []
    for item in context.catalog.items:
        if item.coverage_name is None:
            continue
        normalized = canonicalize_coverage_name(item.coverage_name).normalized_key
        if normalized in duplicate_fixed or (item.policy_id, normalized) in duplicate_actual_loss:
            matched.append(item)
    if matched:
        return tuple(matched)

    no_overlap = context.catalog.by_id.get("portfolio:no-overlap")
    return (no_overlap,) if no_overlap is not None else ()


def portfolio_snapshot_evidence(
    context: QaContext,
    *,
    max_items: int = 24,
) -> tuple[ConsultationEvidence, ...]:
    """Return a bounded portfolio snapshot only after the agent requests it."""

    return context.catalog.items[:max_items]


def _evidence_identities(item: ConsultationEvidence) -> set[str]:
    return {
        canonicalize_coverage_name(value).normalized_key
        for value in (item.coverage_name, item.insurer, item.product_name)
        if value and value.strip()
    }
