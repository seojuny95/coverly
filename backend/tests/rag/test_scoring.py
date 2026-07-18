from dataclasses import dataclass

import pytest

from app.rag.scoring import (
    cosine_similarity,
    rank_positions,
    reciprocal_rank_fusion_score,
)


@dataclass(frozen=True)
class _Chunk:
    id: str


@dataclass(frozen=True)
class _Hit:
    chunk: _Chunk
    score: float


def test_rank_positions_returns_one_based_chunk_ranks() -> None:
    hits = [_Hit(_Chunk("lower"), 0.1), _Hit(_Chunk("higher"), 0.9)]

    assert rank_positions(hits, key=lambda hit: (-hit.score, hit.chunk.id)) == {
        "higher": 1,
        "lower": 2,
    }


def test_reciprocal_rank_fusion_score_uses_shared_constant() -> None:
    assert reciprocal_rank_fusion_score(1, 2) == pytest.approx(1 / 21 + 1 / 22)


def test_cosine_similarity_requires_equal_vector_lengths() -> None:
    assert cosine_similarity((0.6, 0.8), (0.6, 0.8)) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        cosine_similarity((1.0,), (1.0, 0.0))
