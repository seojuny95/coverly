"""Load official source files and turn them into raw chunks.

This file owns file formats: PDF text extraction and law XML parsing. It does
not embed, store, or rank anything.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from functools import lru_cache

import pdfplumber

from app.services.rag.chunking import build_chunks, split_within_char_limit
from app.services.rag.models import RagChunk
from app.services.rag.sources import OfficialSource, rag_sources


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
        if source.absolute_path.suffix.casefold() == ".xml":
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
    root = ET.fromstring(source.absolute_path.read_text(encoding="utf-8"))
    chunks: list[RagChunk] = []
    for index, article in enumerate(root.findall(".//조문단위"), start=1):
        if article.findtext("조문여부") != "조문":
            continue
        number = (article.findtext("조문번호") or "").strip()
        branch = (article.findtext("조문가지번호") or "").strip()
        article_no = f"{number}조의{branch}" if branch else f"{number}조"
        title = (article.findtext("조문제목") or "").strip()
        body = _law_article_text(article)
        if len(body) < 30:
            continue
        label = f"제{article_no}({title})" if title else f"제{article_no}"
        blocks = split_within_char_limit(body)
        base_id = f"{source.id}:{article_no if number else index}"
        for block_index, block in enumerate(blocks, start=1):
            chunk_id = base_id if len(blocks) == 1 else f"{base_id}:{block_index}"
            chunks.append(
                RagChunk(
                    id=chunk_id,
                    source_id=source.id,
                    source_title=source.title,
                    source_category=source.category,
                    publisher=source.publisher,
                    text=block,
                    page_start=index,
                    page_end=index,
                    label=label,
                    citation_label=f"{source.title} {label}",
                    version_label=source.version_label,
                    source_url=source.source_url,
                    local_path=source.local_path,
                )
            )
    return chunks


def _law_article_text(article: ET.Element) -> str:
    values: list[str] = []
    for tag in ("조문내용", "조문참고자료"):
        text = article.findtext(tag)
        if text and text.strip():
            values.append(" ".join(text.split()))
    for element in (
        article.findall(".//항내용") + article.findall(".//호내용") + article.findall(".//목내용")
    ):
        if element.text and element.text.strip():
            values.append(" ".join(element.text.split()))
    return "\n".join(dict.fromkeys(values))
