"""Build searchable text and table chunks from one parsed policy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.core.tables import serialize_table
from app.rag.policy.models import PolicyContentType
from app.rag.text import normalize_text, split_within_char_limit


@dataclass(frozen=True)
class PolicySourceChunk:
    text: str
    content_type: PolicyContentType
    table_index: int | None = None


class PolicyDocument(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def tables(self) -> Sequence[Sequence[Sequence[str | None]]]: ...


def build_policy_source_chunks(doc: PolicyDocument) -> tuple[PolicySourceChunk, ...]:
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
