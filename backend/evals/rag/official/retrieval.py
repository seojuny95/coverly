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
from argparse import ArgumentParser
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from app.rag.embeddings import HashingEmbedder
from app.rag.official.loaders import load_official_chunks
from app.rag.official.models import RagChunk, RetrievalHit, chunk_embedding_text
from app.rag.official.retrieval import retrieve
from evals.rag.data import string_tuple as _string_tuple

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
    accepted_evidence: tuple[AcceptedEvidence, ...] = ()
    expected_no_hits: bool = False


@dataclass(frozen=True)
class AcceptedEvidence:
    source_ids: tuple[str, ...] = ()
    source_categories: tuple[str, ...] = ()
    required_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalEvalResult:
    case_id: str
    passed: bool
    exact_matched: bool
    accepted_matched: bool
    rank: int | None
    accepted_rank: int | None
    recall_at_k: float
    accepted_recall_at_k: float
    precision_at_k: float
    ndcg_at_k: float
    hit_chunk_ids: tuple[str, ...]
    missing_chunk_ids: tuple[str, ...]
    expected_no_hits: bool


@dataclass(frozen=True)
class RetrievalEvalReport:
    passed: int
    total: int
    total_cases: int
    reciprocal_rank_sum: float
    recall_sum: float
    precision_sum: float
    ndcg_sum: float
    diagnostic_negative_no_hit_count: int
    diagnostic_negative_total: int
    elapsed_seconds: float
    results: tuple[RetrievalEvalResult, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def recall(self) -> float:
        return self.recall_sum / self.total if self.total else 0.0

    @property
    def exact_recall(self) -> float:
        return self.recall

    @property
    def accepted_recall(self) -> float:
        positives = tuple(result for result in self.results if not result.expected_no_hits)
        return _rate(result.accepted_recall_at_k for result in positives)

    @property
    def accepted_pass_rate(self) -> float:
        positives = tuple(result for result in self.results if not result.expected_no_hits)
        return _rate(result.passed for result in positives)

    @property
    def mrr(self) -> float:
        return self.reciprocal_rank_sum / self.total if self.total else 0.0

    @property
    def precision_at_k(self) -> float:
        return self.precision_sum / self.total if self.total else 0.0

    @property
    def ndcg_at_k(self) -> float:
        return self.ndcg_sum / self.total if self.total else 0.0

    @property
    def diagnostic_negative_no_hit_rate(self) -> float:
        if not self.diagnostic_negative_total:
            return 0.0
        return self.diagnostic_negative_no_hit_count / self.diagnostic_negative_total

    @property
    def average_latency_seconds(self) -> float:
        return self.elapsed_seconds / self.total_cases if self.total_cases else 0.0


def load_retrieval_eval_cases(path: Path = EVAL_FIXTURE) -> tuple[RetrievalEvalCase, ...]:
    raw_scenarios = cast(list[dict[str, object]], json.loads(path.read_text(encoding="utf-8")))
    cases: list[RetrievalEvalCase] = []

    for raw in raw_scenarios:
        scenario_id = str(raw["id"])
        profile = _profile(raw["profile"])
        difficulty = _difficulty(raw["difficulty"])
        relevant_chunk_ids = _string_tuple(raw["relevant_chunk_ids"])
        accepted_evidence = _accepted_evidence(raw.get("accepted_evidence", []))
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
                    accepted_evidence=accepted_evidence,
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
        passed=sum(result.passed for result in positives),
        total=len(positives),
        total_cases=len(results),
        reciprocal_rank_sum=sum(1 / result.rank for result in positives if result.rank is not None),
        recall_sum=sum(result.recall_at_k for result in positives),
        precision_sum=sum(result.precision_at_k for result in positives),
        ndcg_sum=sum(result.ndcg_at_k for result in positives),
        diagnostic_negative_no_hit_count=sum(result.passed for result in negatives),
        diagnostic_negative_total=len(negatives),
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
            exact_matched=not top_hits,
            accepted_matched=not top_hits,
            rank=None,
            accepted_rank=None,
            recall_at_k=0.0,
            accepted_recall_at_k=0.0,
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
    accepted_rank = rank or _accepted_rank(case, top_hits)
    recall_at_k = 1.0 if retrieved_relevant else 0.0
    accepted_recall_at_k = 1.0 if accepted_rank is not None else 0.0
    precision_at_k = len(retrieved_relevant) / len(top_hits) if top_hits else 0.0
    ndcg_at_k = _ndcg(hit_chunk_ids, relevant)

    return RetrievalEvalResult(
        case_id=case.id,
        passed=accepted_rank is not None,
        exact_matched=rank is not None,
        accepted_matched=accepted_rank is not None,
        rank=rank,
        accepted_rank=accepted_rank,
        recall_at_k=recall_at_k,
        accepted_recall_at_k=accepted_recall_at_k,
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


def _accepted_evidence(value: object) -> tuple[AcceptedEvidence, ...]:
    raw_items = cast(list[dict[str, object]], value)
    return tuple(
        AcceptedEvidence(
            source_ids=_string_tuple(raw.get("source_ids", [])),
            source_categories=_string_tuple(raw.get("source_categories", [])),
            required_terms=_string_tuple(raw.get("required_terms", [])),
        )
        for raw in raw_items
    )


def _accepted_rank(case: RetrievalEvalCase, hits: list[RetrievalHit]) -> int | None:
    for index, hit in enumerate(hits, start=1):
        if _accepted_hit(case, hit):
            return index
    return None


def _accepted_hit(case: RetrievalEvalCase, hit: RetrievalHit) -> bool:
    if not case.accepted_evidence:
        return False
    for accepted in case.accepted_evidence:
        if accepted.source_ids and hit.chunk.source_id not in accepted.source_ids:
            continue
        if (
            accepted.source_categories
            and hit.chunk.source_category not in accepted.source_categories
        ):
            continue
        text = chunk_embedding_text(hit.chunk)
        if all(_contains_normalized(text, term) for term in accepted.required_terms):
            return True
    return False


def _contains_normalized(text: str, term: str) -> bool:
    return _normalize_text(term) in _normalize_text(text)


def _normalize_text(value: str) -> str:
    return "".join(value.split()).casefold()


def _rate(values: Iterable[float]) -> float:
    items = tuple(values)
    return sum(items) / len(items) if items else 0.0


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


def main() -> None:
    parser = ArgumentParser(description="Evaluate official-source RAG retrieval.")
    parser.add_argument(
        "--production",
        action="store_true",
        help="Use the configured OpenAI embedding model and pgvector index.",
    )
    parser.add_argument("--show-passing", action="store_true")
    args = parser.parse_args()

    report = evaluate_retrieval(production=args.production)
    print(
        " ".join(
            [
                f"positive_passed={report.passed}/{report.total}",
                f"accepted_pass={report.accepted_pass_rate:.3f}",
                f"recall@{EVAL_K}={report.recall:.3f}",
                f"accepted_recall@{EVAL_K}={report.accepted_recall:.3f}",
                f"precision@{EVAL_K}={report.precision_at_k:.3f}",
                f"mrr={report.mrr:.3f}",
                f"ndcg@{EVAL_K}={report.ndcg_at_k:.3f}",
                f"diagnostic_negative_no_hit={report.diagnostic_negative_no_hit_rate:.3f}",
                f"total_cases={report.total_cases}",
                f"avg_latency={report.average_latency_seconds:.3f}s",
            ]
        )
    )
    for result in report.results:
        if result.expected_no_hits:
            if not args.show_passing:
                continue
            status = "DIAG_NO_HIT" if result.passed else "DIAG_HIT"
            print(f"{status} {result.case_id} hits={result.hit_chunk_ids}")
            continue
        if result.passed and not args.show_passing:
            continue
        status = "PASS" if result.passed else "FAIL"
        print(f"{status} {result.case_id} rank={result.rank} hits={result.hit_chunk_ids}")


if __name__ == "__main__":
    main()
