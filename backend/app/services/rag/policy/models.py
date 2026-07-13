"""Data shapes for uploaded-policy RAG."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

PolicyContentType = Literal["text", "table"]


@dataclass(frozen=True)
class PolicyChunk:
    id: str
    session_id: str
    text: str
    content_type: PolicyContentType
    chunk_index: int
    table_index: int | None
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class PolicyVectorRecord:
    chunk: PolicyChunk
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class PolicyRetrievalHit:
    chunk: PolicyChunk
    score: float
