"""Compatibility imports for insurer reference-data helpers."""

from app.modules.reference_data.insurers import (
    canonical_insurer_name,
    get_insurer_aliases,
    get_insurer_candidates,
    get_insurer_contact_evidence,
    insurer_name_is_grounded,
    match_insurer_from_text,
)

__all__ = [
    "canonical_insurer_name",
    "get_insurer_aliases",
    "get_insurer_candidates",
    "get_insurer_contact_evidence",
    "insurer_name_is_grounded",
    "match_insurer_from_text",
]
