"""Chunk standard insurance terms while preserving product section context."""

from __future__ import annotations

import re

from app.rag.official.chunkers.common import make_chunk
from app.rag.official.chunkers.consumer_guide import build_consumer_guide_chunks
from app.rag.official.models import RagChunk
from app.rag.official.sources import OfficialSource
from app.rag.text import normalize_text, split_within_char_limit

_ARTICLE_RE = re.compile(r"제\s*\d+\s*조\s*\([^)]*\)")
_TOC_LINE_RE = re.compile(
    r"^[\s\-–]*(?:[Ⅰ-Ⅹ\dⓐ-ⓩ]+\s*[.)]\s*)?"
    r"(?P<label>[가-힣A-Za-z0-9()·\s]+?)\s*[·.…]{3,}\s*(?P<page>\d+)\s*$"
)
_MIN_ARTICLE_BODY_CHARS = 30


def build_standard_terms_chunks(source: OfficialSource, pages: list[str]) -> list[RagChunk]:
    toc = _parse_toc(pages[0] if pages else "")
    if not toc:
        return build_consumer_guide_chunks(source, pages)

    chunks: list[RagChunk] = []
    total_pages = len(pages)
    for index, (section_label, start_page) in enumerate(toc):
        end_page = toc[index + 1][1] - 1 if index + 1 < len(toc) else total_pages
        section_text = normalize_text("\n".join(pages[start_page - 1 : end_page]))
        order = 0
        for article_title, article_text in _split_articles(section_text):
            for block in split_within_char_limit(article_text):
                order += 1
                text = f"[{section_label} > {article_title}]\n{block}"
                chunks.append(
                    make_chunk(
                        source,
                        page_start=start_page,
                        page_end=end_page,
                        order=order,
                        text=text,
                        label=article_title,
                        citation_label=f"{source.title} {section_label} {article_title}",
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
