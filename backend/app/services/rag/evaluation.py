"""Evaluation helpers for official-source RAG retrieval.

This file loads the JSON evaluation set and computes simple pass/fail retrieval
metrics. Human-readable reporting lives in diagnostics.py.

By default this measures ``retrieve()``'s in-memory BM25 + hashing-embedder
path, not the pgvector + OpenAI embeddings path production traffic actually
uses — recall numbers here describe ranking logic quality, not production
retrieval quality. ``retrieve()`` itself has no test-only defaults, so this
file picks the offline ``HashingEmbedder`` explicitly. Pass ``production=True``
to run cases through the real pgvector index instead; that mode calls OpenAI
and needs a populated index, so it must never run inside the unit test suite
(see backend CLAUDE.md's "유닛 테스트가 실제 API를 호출하면 안 된다").
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.services.rag.embeddings import HashingEmbedder
from app.services.rag.loaders import load_official_chunks
from app.services.rag.models import RagChunk, RetrievalHit
from app.services.rag.retrieval import retrieve

EVAL_FIXTURE = Path(__file__).resolve().parent / "retrieval_eval.json"


@dataclass(frozen=True)
class RetrievalEvalCase:
    id: str
    query: str
    expected_source_ids: tuple[str, ...]
    expected_terms: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalEvalResult:
    case_id: str
    passed: bool
    hit_source_ids: tuple[str, ...]
    missing_source_ids: tuple[str, ...]
    missing_terms: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalEvalReport:
    passed: int
    total: int
    results: tuple[RetrievalEvalResult, ...]

    @property
    def recall(self) -> float:
        if self.total == 0:
            return 0.0

        return self.passed / self.total


def load_retrieval_eval_cases(path: Path = EVAL_FIXTURE) -> tuple[RetrievalEvalCase, ...]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases: list[RetrievalEvalCase] = []

    for raw in raw_cases:
        cases.append(
            RetrievalEvalCase(
                id=str(raw["id"]),
                query=str(raw["query"]),
                expected_source_ids=tuple(str(item) for item in raw["expected_source_ids"]),
                expected_terms=tuple(str(item) for item in raw["expected_terms"]),
            )
        )

    return tuple(cases)


def evaluate_retrieval(
    cases: tuple[RetrievalEvalCase, ...] | None = None,
    *,
    production: bool = False,
) -> RetrievalEvalReport:
    active_cases = cases or load_retrieval_eval_cases()
    chunks = None if production else load_official_chunks()
    results = tuple(_evaluate_case(case, _retrieve_for_case(case, chunks)) for case in active_cases)

    return RetrievalEvalReport(
        passed=sum(1 for result in results if result.passed),
        total=len(results),
        results=results,
    )


def _retrieve_for_case(
    case: RetrievalEvalCase, chunks: tuple[RagChunk, ...] | None
) -> list[RetrievalHit]:
    if chunks is None:
        return retrieve(query=case.query)
    return retrieve(query=case.query, chunks=chunks, embedder=HashingEmbedder())


def _evaluate_case(case: RetrievalEvalCase, hits: list[RetrievalHit]) -> RetrievalEvalResult:
    hit_source_ids = tuple(dict.fromkeys(hit.chunk.source_id for hit in hits))
    rendered = "\n".join(hit.chunk.text for hit in hits)
    missing_source_ids = tuple(
        source_id for source_id in case.expected_source_ids if source_id not in hit_source_ids
    )
    missing_terms = tuple(term for term in case.expected_terms if term not in rendered)

    return RetrievalEvalResult(
        case_id=case.id,
        passed=not missing_source_ids and not missing_terms,
        hit_source_ids=hit_source_ids,
        missing_source_ids=missing_source_ids,
        missing_terms=missing_terms,
    )
