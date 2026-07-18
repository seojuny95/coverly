"""Dispatch official sources to document-type chunkers."""

from __future__ import annotations

from app.rag.official.chunkers.consumer_guide import build_consumer_guide_chunks
from app.rag.official.chunkers.product_explanation import build_product_explanation_chunks
from app.rag.official.chunkers.standard_terms import build_standard_terms_chunks
from app.rag.official.models import RagChunk
from app.rag.official.sources import OfficialSource

_PRODUCT_EXPLANATION_SOURCE_IDS = frozenset(
    {
        "knia_auto_insurance_product_explanation_2024_04_01",
    }
)


def build_chunks(source: OfficialSource, pages: list[str]) -> list[RagChunk]:
    """Build chunks for one PDF official source from extracted page texts."""

    if source.category == "standard_clause":
        return build_standard_terms_chunks(source, pages)
    if source.id in _PRODUCT_EXPLANATION_SOURCE_IDS:
        return build_product_explanation_chunks(source, pages)
    return build_consumer_guide_chunks(source, pages)
