"""Chunk law XML documents by article."""

from __future__ import annotations

from typing import Protocol, cast

from defusedxml.ElementTree import fromstring

from app.rag.official.models import RagChunk
from app.rag.official.sources import OfficialSource
from app.rag.text import split_within_char_limit


class _XmlElement(Protocol):
    text: str | None

    def findall(self, path: str) -> list[_XmlElement]: ...

    def findtext(self, path: str) -> str | None: ...


def build_law_xml_chunks(source: OfficialSource, xml_text: str) -> list[RagChunk]:
    root = cast(
        _XmlElement,
        fromstring(
            xml_text,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        ),
    )
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


def _law_article_text(article: _XmlElement) -> str:
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
