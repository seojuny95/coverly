"""Dispatch official sources to document-type chunkers."""

from __future__ import annotations

from app.rag.official.chunkers.consumer_guide import build_consumer_guide_chunks
from app.rag.official.chunkers.product_explanation import build_product_explanation_chunks
from app.rag.official.chunkers.standard_terms import build_standard_terms_chunks
from app.rag.official.models import RagChunk
from app.rag.official.sources import OfficialSource


def build_chunks(source: OfficialSource, pages: list[str]) -> list[RagChunk]:
    """Build chunks for one PDF official source from extracted page texts."""

    if source.document_type == "standard_terms":
        return build_standard_terms_chunks(source, pages)
    if source.document_type == "product_explanation":
        return build_product_explanation_chunks(source, pages)
    if source.document_type == "consumer_guide":
        return build_consumer_guide_chunks(source, pages)
    raise ValueError(
        f"{source.id}: unsupported PDF official source document_type {source.document_type}"
    )
