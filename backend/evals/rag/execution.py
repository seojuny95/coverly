"""Shared execution metadata for RAG evaluations."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

RetrievalMode = Literal["offline", "production"]
GenerationMode = Literal["deterministic", "live"]


@dataclass(frozen=True)
class RagEvalRunMetadata:
    retrieval_mode: RetrievalMode
    generation_mode: GenerationMode
    retrieval_model: str
    generation_model: str
    corpus_version: str
    index_version: str
    executed_at: datetime
    retrieval_average_latency_seconds: float
    retrieval_p95_latency_seconds: float
    generation_average_latency_seconds: float
    generation_p95_latency_seconds: float
    total_average_latency_seconds: float
    total_p95_latency_seconds: float


def validate_execution_modes(
    retrieval_mode: RetrievalMode,
    generation_mode: GenerationMode,
) -> None:
    if retrieval_mode not in {"offline", "production"}:
        raise ValueError(f"unknown retrieval mode: {retrieval_mode}")
    if generation_mode not in {"deterministic", "live"}:
        raise ValueError(f"unknown generation mode: {generation_mode}")


def build_run_metadata(
    *,
    retrieval_mode: RetrievalMode,
    generation_mode: GenerationMode,
    retrieval_model: str,
    generation_model: str,
    corpus_version: str,
    index_version: str,
    retrieval_latencies: tuple[float, ...],
    generation_latencies: tuple[float, ...],
    executed_at: datetime,
) -> RagEvalRunMetadata:
    total_latencies = tuple(
        retrieval + generation
        for retrieval, generation in zip(
            retrieval_latencies,
            generation_latencies,
            strict=True,
        )
    )
    return RagEvalRunMetadata(
        retrieval_mode=retrieval_mode,
        generation_mode=generation_mode,
        retrieval_model=retrieval_model,
        generation_model=generation_model,
        corpus_version=corpus_version,
        index_version=index_version,
        executed_at=executed_at.astimezone(UTC),
        retrieval_average_latency_seconds=_average(retrieval_latencies),
        retrieval_p95_latency_seconds=_p95(retrieval_latencies),
        generation_average_latency_seconds=_average(generation_latencies),
        generation_p95_latency_seconds=_p95(generation_latencies),
        total_average_latency_seconds=_average(total_latencies),
        total_p95_latency_seconds=_p95(total_latencies),
    )


def content_version(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, byteorder="big"))
        digest.update(encoded)
    return digest.hexdigest()[:16]


def _average(values: tuple[float, ...]) -> float:
    return sum(values) / len(values) if values else 0.0


def _p95(values: tuple[float, ...]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
