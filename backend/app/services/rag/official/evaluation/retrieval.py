"""Evaluation helpers for official-source RAG retrieval.

The dataset labels exact relevant chunk ids instead of source-level terms.
Each scenario expands to multiple query variants so lexical overlap alone does
not define success. Offline evaluation is deterministic; production mode uses
the deployed pgvector and OpenAI embedding path.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from app.services.rag.embeddings import HashingEmbedder
from app.services.rag.official.loaders import load_official_chunks
from app.services.rag.official.models import RagChunk, RetrievalHit
from app.services.rag.official.retrieval import retrieve

EVAL_FIXTURE = Path(__file__).resolve().parent / "retrieval_dataset.json"
EVAL_K = 5

RetrievalProfile = Literal["term_explain", "claim_check", "consumer_protection", "out_of_scope"]
RetrievalDifficulty = Literal["easy", "medium", "hard"]


@dataclass(frozen=True)
class RetrievalEvalCase:
    id: str
    query: str
    profile: RetrievalProfile
    difficulty: RetrievalDifficulty
    relevant_chunk_ids: tuple[str, ...]
    expected_no_hits: bool = False


@dataclass(frozen=True)
class RetrievalEvalResult:
    case_id: str
    passed: bool
    rank: int | None
    recall_at_k: float
    precision_at_k: float
    ndcg_at_k: float
    hit_chunk_ids: tuple[str, ...]
    missing_chunk_ids: tuple[str, ...]
    expected_no_hits: bool


@dataclass(frozen=True)
class RetrievalEvalReport:
    passed: int
    total: int
    reciprocal_rank_sum: float
    recall_sum: float
    precision_sum: float
    ndcg_sum: float
    negative_passed: int
    negative_total: int
    elapsed_seconds: float
    results: tuple[RetrievalEvalResult, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def recall(self) -> float:
        positive_total = self.total - self.negative_total
        return self.recall_sum / positive_total if positive_total else 0.0

    @property
    def mrr(self) -> float:
        positive_total = self.total - self.negative_total
        return self.reciprocal_rank_sum / positive_total if positive_total else 0.0

    @property
    def precision_at_k(self) -> float:
        positive_total = self.total - self.negative_total
        return self.precision_sum / positive_total if positive_total else 0.0

    @property
    def ndcg_at_k(self) -> float:
        positive_total = self.total - self.negative_total
        return self.ndcg_sum / positive_total if positive_total else 0.0

    @property
    def negative_no_hit_rate(self) -> float:
        return self.negative_passed / self.negative_total if self.negative_total else 0.0

    @property
    def average_latency_seconds(self) -> float:
        return self.elapsed_seconds / self.total if self.total else 0.0


def load_retrieval_eval_cases(path: Path = EVAL_FIXTURE) -> tuple[RetrievalEvalCase, ...]:
    raw_scenarios = cast(list[dict[str, object]], json.loads(path.read_text(encoding="utf-8")))
    cases: list[RetrievalEvalCase] = []

    for raw in raw_scenarios:
        scenario_id = str(raw["id"])
        profile = _profile(raw["profile"])
        difficulty = _difficulty(raw["difficulty"])
        relevant_chunk_ids = _string_tuple(raw["relevant_chunk_ids"])
        expected_no_hits = bool(raw.get("expected_no_hits", False))
        questions = _string_tuple(raw["questions"])
        for index, question in enumerate(questions, start=1):
            cases.append(
                RetrievalEvalCase(
                    id=f"{scenario_id}__q{index}",
                    query=question,
                    profile=profile,
                    difficulty=difficulty,
                    relevant_chunk_ids=relevant_chunk_ids,
                    expected_no_hits=expected_no_hits,
                )
            )

    return tuple(cases)


def evaluate_retrieval(
    cases: tuple[RetrievalEvalCase, ...] | None = None,
    *,
    production: bool = False,
) -> RetrievalEvalReport:
    active_cases = cases if cases is not None else load_retrieval_eval_cases()
    chunks = None if production else load_official_chunks()
    started = time.perf_counter()
    results = tuple(_evaluate_case(case, _retrieve_for_case(case, chunks)) for case in active_cases)
    elapsed_seconds = time.perf_counter() - started
    positives = tuple(result for result in results if not result.expected_no_hits)
    negatives = tuple(result for result in results if result.expected_no_hits)

    return RetrievalEvalReport(
        passed=sum(result.passed for result in results),
        total=len(results),
        reciprocal_rank_sum=sum(1 / result.rank for result in positives if result.rank is not None),
        recall_sum=sum(result.recall_at_k for result in positives),
        precision_sum=sum(result.precision_at_k for result in positives),
        ndcg_sum=sum(result.ndcg_at_k for result in positives),
        negative_passed=sum(result.passed for result in negatives),
        negative_total=len(negatives),
        elapsed_seconds=elapsed_seconds,
        results=results,
    )


def _retrieve_for_case(
    case: RetrievalEvalCase, chunks: tuple[RagChunk, ...] | None
) -> list[RetrievalHit]:
    if chunks is None:
        return retrieve(query=case.query, final_k=EVAL_K)
    return retrieve(
        query=case.query,
        chunks=chunks,
        embedder=HashingEmbedder(),
        final_k=EVAL_K,
    )


def _evaluate_case(case: RetrievalEvalCase, hits: list[RetrievalHit]) -> RetrievalEvalResult:
    top_hits = hits[:EVAL_K]
    hit_chunk_ids = tuple(hit.chunk.id for hit in top_hits)
    relevant = set(case.relevant_chunk_ids)

    if case.expected_no_hits:
        return RetrievalEvalResult(
            case_id=case.id,
            passed=not top_hits,
            rank=None,
            recall_at_k=0.0,
            precision_at_k=0.0,
            ndcg_at_k=0.0,
            hit_chunk_ids=hit_chunk_ids,
            missing_chunk_ids=(),
            expected_no_hits=True,
        )

    retrieved_relevant = relevant.intersection(hit_chunk_ids)
    rank = next(
        (index for index, chunk_id in enumerate(hit_chunk_ids, start=1) if chunk_id in relevant),
        None,
    )
    recall_at_k = 1.0 if retrieved_relevant else 0.0
    precision_at_k = len(retrieved_relevant) / len(top_hits) if top_hits else 0.0
    ndcg_at_k = _ndcg(hit_chunk_ids, relevant)

    return RetrievalEvalResult(
        case_id=case.id,
        passed=rank is not None,
        rank=rank,
        recall_at_k=recall_at_k,
        precision_at_k=precision_at_k,
        ndcg_at_k=ndcg_at_k,
        hit_chunk_ids=hit_chunk_ids,
        missing_chunk_ids=() if retrieved_relevant else case.relevant_chunk_ids,
        expected_no_hits=False,
    )


def _ndcg(hit_chunk_ids: tuple[str, ...], relevant: set[str]) -> float:
    if not relevant:
        return 0.0
    dcg = sum(
        1 / math.log2(rank + 1)
        for rank, chunk_id in enumerate(hit_chunk_ids, start=1)
        if chunk_id in relevant
    )
    ideal_count = min(len(relevant), EVAL_K)
    ideal_dcg = sum(1 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    return dcg / ideal_dcg


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(list[object], value))


def _profile(value: object) -> RetrievalProfile:
    profile = str(value)
    if profile not in {"term_explain", "claim_check", "consumer_protection", "out_of_scope"}:
        raise ValueError(f"unknown retrieval profile: {profile}")
    return cast(RetrievalProfile, profile)


def _difficulty(value: object) -> RetrievalDifficulty:
    difficulty = str(value)
    if difficulty not in {"easy", "medium", "hard"}:
        raise ValueError(f"unknown retrieval difficulty: {difficulty}")
    return cast(RetrievalDifficulty, difficulty)
