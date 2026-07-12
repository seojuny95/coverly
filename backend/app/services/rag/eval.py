"""Tiny retrieval evaluation loop for the first RAG iteration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.services.rag.retrieve import RetrievalHit, infer_profile, retrieve

EVAL_FIXTURE = Path(__file__).resolve().parents[3] / "tests/fixtures/rag/retrieval_eval.json"


@dataclass(frozen=True)
class RetrievalEvalCase:
    id: str
    query: str
    expected_source_ids: tuple[str, ...]
    expected_terms: tuple[str, ...]
    profile: str


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
        profile = str(raw.get("profile") or infer_profile(str(raw["query"])))
        cases.append(
            RetrievalEvalCase(
                id=str(raw["id"]),
                query=str(raw["query"]),
                expected_source_ids=tuple(str(item) for item in raw["expected_source_ids"]),
                expected_terms=tuple(str(item) for item in raw["expected_terms"]),
                profile=profile,
            )
        )
    return tuple(cases)


def evaluate_retrieval(cases: tuple[RetrievalEvalCase, ...] | None = None) -> RetrievalEvalReport:
    active_cases = cases or load_retrieval_eval_cases()
    results = tuple(
        _evaluate_case(case, retrieve(query=case.query, profile=case.profile))
        for case in active_cases
    )
    return RetrievalEvalReport(
        passed=sum(1 for result in results if result.passed),
        total=len(results),
        results=results,
    )


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
