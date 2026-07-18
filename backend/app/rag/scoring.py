"""Shared ranking and similarity helpers for RAG retrieval."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

_RRF_K = 20


class _Identified(Protocol):
    @property
    def id(self) -> str: ...


class _ChunkHit(Protocol):
    @property
    def chunk(self) -> _Identified: ...


def rank_positions[ChunkHitT: _ChunkHit](
    hits: list[ChunkHitT],
    *,
    key: Callable[[ChunkHitT], tuple[float | int | str, ...]],
) -> dict[str, int]:
    """Return one-based positions after sorting chunk-backed hits."""

    ordered = sorted(hits, key=key)
    return {hit.chunk.id: rank for rank, hit in enumerate(ordered, start=1)}


def reciprocal_rank_fusion_score(*ranks: int, k: int = _RRF_K) -> float:
    """Combine one-based ranks using reciprocal rank fusion."""

    return sum(1 / (k + rank) for rank in ranks)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Return the dot product for vectors normalized by their embedder."""

    return sum(a * b for a, b in zip(left, right, strict=True))
