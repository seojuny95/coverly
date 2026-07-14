"""Evaluation helpers for official RAG answerability experiments."""

from __future__ import annotations

import time
from argparse import ArgumentParser
from dataclasses import dataclass
from typing import Literal, cast

from app.services.llm import JsonCompleter
from app.services.rag.embeddings import HashingEmbedder
from app.services.rag.official.answerability import (
    EvidenceSufficiencyDecision,
    QueryScopeDecision,
    judge_evidence_sufficiency,
    judge_query_scope,
)
from app.services.rag.official.evaluation.retrieval import (
    EVAL_FIXTURE,
    EVAL_K,
    RetrievalEvalCase,
    load_retrieval_eval_cases,
)
from app.services.rag.official.loaders import load_official_chunks
from app.services.rag.official.models import RagChunk, RetrievalHit
from app.services.rag.official.retrieval import retrieve
from app.settings import get_settings

AnswerabilityExperiment = Literal["scope", "evidence", "cascade"]
AnswerabilityDecision = Literal["accepted", "rejected"]


@dataclass(frozen=True)
class AnswerabilityEvalResult:
    case_id: str
    expected_no_hits: bool
    decision: AnswerabilityDecision
    passed: bool
    scope_label: str | None
    evidence_label: str | None
    supporting_citation_ids: tuple[str, ...]
    hit_chunk_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class AnswerabilityEvalReport:
    experiment: AnswerabilityExperiment
    passed: int
    total: int
    positive_accepted: int
    positive_total: int
    negative_rejected: int
    negative_total: int
    elapsed_seconds: float
    results: tuple[AnswerabilityEvalResult, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def positive_accept_rate(self) -> float:
        return self.positive_accepted / self.positive_total if self.positive_total else 0.0

    @property
    def negative_reject_rate(self) -> float:
        return self.negative_rejected / self.negative_total if self.negative_total else 0.0

    @property
    def average_latency_seconds(self) -> float:
        return self.elapsed_seconds / self.total if self.total else 0.0


def evaluate_answerability(
    cases: tuple[RetrievalEvalCase, ...] | None = None,
    *,
    experiment: AnswerabilityExperiment,
    production: bool = False,
    scope_complete: JsonCompleter | None = None,
    evidence_complete: JsonCompleter | None = None,
) -> AnswerabilityEvalReport:
    """Run an answerability experiment on the retrieval eval cases."""

    if (scope_complete is None or evidence_complete is None) and not get_settings().openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live answerability evaluation")

    active_cases = cases if cases is not None else load_retrieval_eval_cases()
    chunks = None if production else load_official_chunks()
    started = time.perf_counter()
    results = tuple(
        _evaluate_case(
            case,
            experiment=experiment,
            chunks=chunks,
            scope_complete=scope_complete,
            evidence_complete=evidence_complete,
        )
        for case in active_cases
    )
    elapsed_seconds = time.perf_counter() - started

    positives = tuple(result for result in results if not result.expected_no_hits)
    negatives = tuple(result for result in results if result.expected_no_hits)

    return AnswerabilityEvalReport(
        experiment=experiment,
        passed=sum(result.passed for result in results),
        total=len(results),
        positive_accepted=sum(result.decision == "accepted" for result in positives),
        positive_total=len(positives),
        negative_rejected=sum(result.decision == "rejected" for result in negatives),
        negative_total=len(negatives),
        elapsed_seconds=elapsed_seconds,
        results=results,
    )


def render_answerability_report(
    report: AnswerabilityEvalReport,
    *,
    show_passing: bool = False,
) -> str:
    lines = [
        (
            f"experiment={report.experiment} "
            f"passed={report.passed}/{report.total} "
            f"pass_rate={report.pass_rate:.3f} "
            f"positive_accept={report.positive_accepted}/{report.positive_total} "
            f"positive_accept_rate={report.positive_accept_rate:.3f} "
            f"negative_reject={report.negative_rejected}/{report.negative_total} "
            f"negative_reject_rate={report.negative_reject_rate:.3f} "
            f"avg_latency={report.average_latency_seconds:.3f}s"
        )
    ]

    for result in report.results:
        if result.passed and not show_passing:
            continue
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"{status} {result.case_id} decision={result.decision} "
            f"scope={result.scope_label} evidence={result.evidence_label}"
        )
        if result.reason:
            lines.append(f"  - {result.reason}")
        if result.hit_chunk_ids:
            lines.append(f"  hits: {', '.join(result.hit_chunk_ids)}")
        if result.supporting_citation_ids:
            lines.append(f"  supports: {', '.join(result.supporting_citation_ids)}")

    return "\n".join(lines)


def _evaluate_case(
    case: RetrievalEvalCase,
    *,
    experiment: AnswerabilityExperiment,
    chunks: tuple[RagChunk, ...] | None,
    scope_complete: JsonCompleter | None,
    evidence_complete: JsonCompleter | None,
) -> AnswerabilityEvalResult:
    scope = _scope_decision(case, experiment=experiment, complete=scope_complete)
    if scope is not None and scope.label == "out_of_scope":
        return _result(
            case,
            decision="rejected",
            scope=scope,
            evidence=None,
            hits=[],
            reason=scope.reason,
        )

    hits = _retrieve_for_case(case, chunks)
    evidence = _evidence_decision(
        case,
        hits,
        experiment=experiment,
        complete=evidence_complete,
    )
    if evidence is not None and evidence.label == "unanswerable":
        return _result(
            case,
            decision="rejected",
            scope=scope,
            evidence=evidence,
            hits=hits,
            reason=evidence.reason,
        )

    return _result(
        case,
        decision="accepted",
        scope=scope,
        evidence=evidence,
        hits=hits,
        reason=_accepted_reason(scope, evidence),
    )


def _scope_decision(
    case: RetrievalEvalCase,
    *,
    experiment: AnswerabilityExperiment,
    complete: JsonCompleter | None,
) -> QueryScopeDecision | None:
    if experiment not in {"scope", "cascade"}:
        return None
    return judge_query_scope(case.query, complete=complete)


def _evidence_decision(
    case: RetrievalEvalCase,
    hits: list[RetrievalHit],
    *,
    experiment: AnswerabilityExperiment,
    complete: JsonCompleter | None,
) -> EvidenceSufficiencyDecision | None:
    if experiment not in {"evidence", "cascade"}:
        return None
    return judge_evidence_sufficiency(case.query, hits, complete=complete)


def _retrieve_for_case(
    case: RetrievalEvalCase,
    chunks: tuple[RagChunk, ...] | None,
) -> list[RetrievalHit]:
    if chunks is None:
        return retrieve(query=case.query, final_k=EVAL_K)
    return retrieve(
        query=case.query,
        chunks=chunks,
        embedder=HashingEmbedder(),
        final_k=EVAL_K,
    )


def _result(
    case: RetrievalEvalCase,
    *,
    decision: AnswerabilityDecision,
    scope: QueryScopeDecision | None,
    evidence: EvidenceSufficiencyDecision | None,
    hits: list[RetrievalHit],
    reason: str,
) -> AnswerabilityEvalResult:
    passed = decision == ("rejected" if case.expected_no_hits else "accepted")
    return AnswerabilityEvalResult(
        case_id=case.id,
        expected_no_hits=case.expected_no_hits,
        decision=decision,
        passed=passed,
        scope_label=scope.label if scope is not None else None,
        evidence_label=evidence.label if evidence is not None else None,
        supporting_citation_ids=(
            tuple(evidence.supporting_citation_ids) if evidence is not None else ()
        ),
        hit_chunk_ids=tuple(hit.chunk.id for hit in hits[:EVAL_K]),
        reason=reason,
    )


def _accepted_reason(
    scope: QueryScopeDecision | None,
    evidence: EvidenceSufficiencyDecision | None,
) -> str:
    reasons = [decision.reason for decision in (scope, evidence) if decision is not None]
    return " / ".join(reasons)


def _parse_args() -> tuple[AnswerabilityExperiment, bool, bool]:
    parser = ArgumentParser(description="Evaluate official RAG answerability gates.")
    parser.add_argument(
        "experiment",
        choices=("scope", "evidence", "cascade"),
        help="answerability experiment to run",
    )
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--show-passing", action="store_true")
    args = parser.parse_args()
    return (
        cast(AnswerabilityExperiment, args.experiment),
        bool(args.production),
        bool(args.show_passing),
    )


if __name__ == "__main__":
    experiment, production, show_passing = _parse_args()
    report = evaluate_answerability(
        load_retrieval_eval_cases(EVAL_FIXTURE),
        experiment=experiment,
        production=production,
    )
    print(render_answerability_report(report, show_passing=show_passing))
