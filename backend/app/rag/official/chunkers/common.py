"""Shared helpers for official-source chunkers."""

from __future__ import annotations

import hashlib
import re

from app.rag.official.models import RagChunk
from app.rag.official.sources import OfficialSource

_SECTION_HEADING_RE = re.compile(r"^(?:[Ⅰ-Ⅹ]+|[0-9]+)\s+[^\n]{2,80}$")


def make_chunk(
    source: OfficialSource,
    *,
    page_start: int,
    page_end: int,
    order: int,
    text: str,
    label: str | None,
    citation_label: str,
) -> RagChunk:
    key = f"{source.id}|{page_start}|{page_end}|{order}|{text}"
    digest = hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()
    return RagChunk(
        id=digest[:20],
        source_id=source.id,
        source_title=source.title,
        source_category=source.category,
        publisher=source.publisher,
        text=text,
        page_start=page_start,
        page_end=page_end,
        label=label,
        citation_label=citation_label,
        version_label=source.version_label,
        source_url=source.source_url,
        local_path=source.local_path,
    )


def first_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:80]
    return None


def split_heading_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if _SECTION_HEADING_RE.match(line.strip())]
    if len(starts) < 2:
        return []

    blocks: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        blocks.append("\n".join(lines[start:end]))
    return blocks
