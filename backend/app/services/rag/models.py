"""Shared data shapes for the official-source RAG flow.

Keep plain dataclasses here so indexing, retrieval, generation, and evaluation
can share the same vocabulary without importing each other's pipeline code.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RagChunk:
    """One searchable, citation-ready piece of an official source."""

    id: str
    source_id: str
    source_title: str
    source_category: str
    publisher: str
    text: str
    page_start: int
    page_end: int
    label: str | None = None
    citation_label: str | None = None
    version_label: str | None = None
    source_url: str | None = None
    local_path: str | None = None


@dataclass(frozen=True)
class VectorRecord:
    """A chunk plus its embedding, ready to store or search."""

    chunk: RagChunk
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class QueryPlan:
    """The search form of a user question."""

    original_query: str
    search_query: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalHit:
    """One retrieved chunk with both keyword and vector scores."""

    chunk: RagChunk
    score: float
    keyword_score: float
    vector_score: float
