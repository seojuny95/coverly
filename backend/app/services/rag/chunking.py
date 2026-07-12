"""Chunk official insurance sources into citation-ready text units.

This file only decides chunk boundaries and citation labels. It does not load
files, create embeddings, or search.
"""

from __future__ import annotations

import hashlib
import re

from app.services.rag.models import RagChunk
from app.services.rag.sources import OfficialSource

_ARTICLE_RE = re.compile(r"제\s*\d+\s*조\s*\([^)]*\)")
_TOC_LINE_RE = re.compile(
    r"^[\s\-–]*(?:[Ⅰ-Ⅹ\dⓐ-ⓩ]+\s*[.)]\s*)?"
    r"(?P<label>[가-힣A-Za-z0-9()·\s]+?)\s*[·.…]{3,}\s*(?P<page>\d+)\s*$"
)
_SECTION_HEADING_RE = re.compile(r"^(?:[Ⅰ-Ⅹ]+|[0-9]+)\s+[^\n]{2,80}$")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_MIN_ARTICLE_BODY_CHARS = 30
_MAX_PAGE_CHUNK_CHARS = 1400


def build_chunks(source: OfficialSource, pages: list[str]) -> list[RagChunk]:
    """Build chunks for one official source from extracted page texts."""
    if source.category == "standard_clause":
        return _standard_clause_chunks(source, pages)
    return _page_or_section_chunks(source, pages)


def normalize_text(text: str) -> str:
    lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in text.splitlines()]
    kept: list[str] = []
    for line in lines:
        if line:
            kept.append(line)
        elif kept and kept[-1] != "":
            kept.append("")
    return "\n".join(kept).strip()


def _standard_clause_chunks(source: OfficialSource, pages: list[str]) -> list[RagChunk]:
    toc = _parse_toc(pages[0] if pages else "")
    chunks: list[RagChunk] = []
    if not toc:
        return _page_or_section_chunks(source, pages)

    total_pages = len(pages)
    for index, (label, start_page) in enumerate(toc):
        end_page = toc[index + 1][1] - 1 if index + 1 < len(toc) else total_pages
        section_text = normalize_text("\n".join(pages[start_page - 1 : end_page]))
        order = 0
        for article_title, article_text in _split_articles(section_text):
            for block in split_within_char_limit(article_text):
                order += 1
                text = f"[{label} > {article_title}]\n{block}"
                chunks.append(
                    _chunk(
                        source,
                        page_start=start_page,
                        page_end=end_page,
                        order=order,
                        text=text,
                        label=article_title,
                        citation_label=f"{source.title} {article_title}",
                    )
                )
    return chunks


def _page_or_section_chunks(source: OfficialSource, pages: list[str]) -> list[RagChunk]:
    chunks: list[RagChunk] = []
    for page_no, raw_text in enumerate(pages, start=1):
        text = normalize_text(raw_text)
        if not text:
            continue
        blocks = _split_heading_blocks(text) or split_within_char_limit(text)
        for order, block in enumerate(blocks, start=1):
            normalized = normalize_text(block)
            if len(normalized) < 40:
                continue
            chunks.append(
                _chunk(
                    source,
                    page_start=page_no,
                    page_end=page_no,
                    order=order,
                    text=normalized,
                    label=_first_line(normalized),
                    citation_label=f"{source.title} p.{page_no}",
                )
            )
    return chunks


def _parse_toc(toc_text: str) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    for raw in toc_text.splitlines():
        match = _TOC_LINE_RE.match(raw.strip())
        if not match:
            continue
        label = match.group("label").strip()
        if label:
            entries.append((label, int(match.group("page"))))
    return entries


def _split_articles(text: str) -> list[tuple[str, str]]:
    matches = list(_ARTICLE_RE.finditer(text))
    chunks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = re.sub(r"\s+", " ", match.group()).strip()
        body = text[match.start() : end].strip()
        after_title = body[len(match.group()) :].strip(" ,·및또는\n\t")
        if len(after_title) < _MIN_ARTICLE_BODY_CHARS:
            continue
        chunks.append((title, body))
    return chunks


def _split_heading_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if _SECTION_HEADING_RE.match(line.strip())]
    if len(starts) < 2:
        return []
    blocks: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        blocks.append("\n".join(lines[start:end]))
    return blocks


def split_within_char_limit(text: str) -> list[str]:
    if len(text) <= _MAX_PAGE_CHUNK_CHARS:
        return [text]
    units = [unit.strip() for unit in text.split("\n\n") if unit.strip()]
    return _pack_units(units) or [text[:_MAX_PAGE_CHUNK_CHARS]]


def _pack_units(units: list[str]) -> list[str]:
    """Greedily pack units under the size cap, splitting oversized units first."""
    blocks: list[str] = []
    current = ""
    for unit in units:
        for piece in _fit_unit(unit):
            candidate = f"{current}\n{piece}" if current else piece
            if current and len(candidate) > _MAX_PAGE_CHUNK_CHARS:
                blocks.append(current)
                current = piece
                continue
            current = candidate
    if current:
        blocks.append(current)
    return blocks


def _fit_unit(unit: str) -> list[str]:
    """Split one over-cap unit by line, then hard-slice as a last resort.

    A unit here is a paragraph (or, on retry, a line). Real annex tables can
    run for pages without a blank line between rows, so falling back to plain
    character slicing keeps every chunk under the OpenAI embedding input limit.
    """
    if len(unit) <= _MAX_PAGE_CHUNK_CHARS:
        return [unit]

    lines = [line.strip() for line in unit.split("\n") if line.strip()]
    if len(lines) > 1:
        return _pack_units(lines)

    return [
        unit[start : start + _MAX_PAGE_CHUNK_CHARS]
        for start in range(0, len(unit), _MAX_PAGE_CHUNK_CHARS)
    ]


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:80]
    return None


def _chunk(
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
    digest = hashlib.sha1(key.encode()).hexdigest()
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
