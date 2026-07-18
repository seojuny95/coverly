"""Chunk product explanation PDFs by visible sections."""

from __future__ import annotations

import re

from app.rag.official.chunkers.common import first_line, make_chunk, split_heading_blocks
from app.rag.official.models import RagChunk
from app.rag.official.sources import OfficialSource
from app.rag.text import normalize_text, split_within_char_limit

_PRODUCT_SECTION_RE = re.compile(
    r"^(?:"
    r"▣\s*.+|"
    r"주\s*의!\s*.+|"
    r"설명서\s+\d+\s+.+|"
    r"\d+\s+[가-힣A-Za-z].{4,}"
    r")$"
)


def build_product_explanation_chunks(source: OfficialSource, pages: list[str]) -> list[RagChunk]:
    chunks: list[RagChunk] = []
    for page_no, raw_text in enumerate(pages, start=1):
        text = normalize_text(raw_text)
        if not text:
            continue

        blocks = (
            _split_product_sections(text)
            or split_heading_blocks(text)
            or split_within_char_limit(text)
        )
        for order, block in enumerate(blocks, start=1):
            normalized = normalize_text(block)
            if len(normalized) < 40:
                continue
            label = first_line(normalized)
            chunks.append(
                make_chunk(
                    source,
                    page_start=page_no,
                    page_end=page_no,
                    order=order,
                    text=normalized,
                    label=label,
                    citation_label=f"{source.title} p.{page_no}",
                )
            )
    return chunks


def _split_product_sections(text: str) -> list[str]:
    lines = text.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if _PRODUCT_SECTION_RE.match(line.strip()) is not None
    ]
    if len(starts) < 2:
        return []

    blocks: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        if block:
            blocks.extend(split_within_char_limit(block))
    return blocks
