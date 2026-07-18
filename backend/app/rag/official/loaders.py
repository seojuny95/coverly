"""Load official source files and turn them into raw chunks.

This file owns file formats: PDF text extraction and law XML parsing. It does
not embed, store, or rank anything.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

import pdfplumber

from app.rag.official.chunkers import build_chunks
from app.rag.official.chunkers.law import build_law_xml_chunks
from app.rag.official.models import RagChunk
from app.rag.official.sources import OfficialSource, rag_sources


@lru_cache(maxsize=1)
def load_official_chunks() -> tuple[RagChunk, ...]:
    """Load every enabled official source into citation-ready chunks."""

    return tuple(_iter_official_chunks())


def _iter_official_chunks() -> Iterable[RagChunk]:
    for source in rag_sources():
        if source.status != "downloaded" or source.absolute_path is None:
            continue
        if not source.absolute_path.exists():
            continue
        if source.document_type == "law":
            yield from _load_law_xml_chunks(source)
        else:
            yield from _load_pdf_chunks(source)


def _load_pdf_chunks(source: OfficialSource) -> list[RagChunk]:
    assert source.absolute_path is not None
    with pdfplumber.open(str(source.absolute_path)) as pdf:
        pages = [(page.extract_text() or "") for page in pdf.pages]
    return build_chunks(source, pages)


def _load_law_xml_chunks(source: OfficialSource) -> list[RagChunk]:
    assert source.absolute_path is not None
    return build_law_xml_chunks(source, source.absolute_path.read_text(encoding="utf-8"))
