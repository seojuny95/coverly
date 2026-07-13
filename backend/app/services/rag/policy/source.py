"""Build searchable text and table chunks from one parsed policy."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.policy.models import ParsedDocument
from app.services.rag.policy.models import PolicyContentType
from app.services.rag.text import normalize_text, split_within_char_limit
from app.services.table_text import serialize_table


@dataclass(frozen=True)
class PolicySourceChunk:
    text: str
    content_type: PolicyContentType
    table_index: int | None = None


def build_policy_source_chunks(doc: ParsedDocument) -> tuple[PolicySourceChunk, ...]:
    chunks: list[PolicySourceChunk] = []

    normalized_text = normalize_text(doc.text)
    if normalized_text:
        chunks.extend(
            PolicySourceChunk(text=part, content_type="text")
            for part in split_within_char_limit(normalized_text)
            if part.strip()
        )

    for table_index, table in enumerate(doc.tables, start=1):
        rendered = serialize_table(table)
        if not rendered:
            continue
        chunks.extend(
            PolicySourceChunk(text=part, content_type="table", table_index=table_index)
            for part in split_within_char_limit(rendered)
            if part.strip()
        )

    return tuple(chunks)
