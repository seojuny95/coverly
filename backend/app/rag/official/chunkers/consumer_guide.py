"""Chunk general consumer guide PDFs."""

from __future__ import annotations

from app.rag.official.chunkers.common import first_line, make_chunk, split_heading_blocks
from app.rag.official.models import RagChunk
from app.rag.official.sources import OfficialSource
from app.rag.text import normalize_text, split_within_char_limit


def build_consumer_guide_chunks(source: OfficialSource, pages: list[str]) -> list[RagChunk]:
    chunks: list[RagChunk] = []
    for page_no, raw_text in enumerate(pages, start=1):
        text = normalize_text(raw_text)
        if not text:
            continue

        blocks = split_heading_blocks(text) or split_within_char_limit(text)
        for order, block in enumerate(blocks, start=1):
            normalized = normalize_text(block)
            if len(normalized) < 40:
                continue
            chunks.append(
                make_chunk(
                    source,
                    page_start=page_no,
                    page_end=page_no,
                    order=order,
                    text=normalized,
                    label=first_line(normalized),
                    citation_label=f"{source.title} p.{page_no}",
                )
            )
    return chunks
