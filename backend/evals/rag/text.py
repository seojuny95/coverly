"""Shared deterministic text checks for RAG evaluations."""

from __future__ import annotations


def normalize_whitespace(text: str) -> str:
    """Collapse whitespace before deterministic substring checks."""

    return " ".join(text.split())


def missing_term_groups(
    groups: tuple[tuple[str, ...], ...],
    text: str,
) -> tuple[str, ...]:
    """Return groups for which none of the accepted terms are present."""

    normalized = normalize_whitespace(text)
    return tuple(
        " / ".join(group)
        for group in groups
        if not any(normalize_whitespace(term) in normalized for term in group)
    )


def present_terms(terms: tuple[str, ...], text: str) -> tuple[str, ...]:
    """Return forbidden terms present in text after whitespace normalization."""

    normalized = normalize_whitespace(text)
    return tuple(term for term in terms if normalize_whitespace(term) in normalized)
