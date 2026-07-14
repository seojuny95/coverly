"""Diagnostic report for official-source RAG retrieval quality.

Like evaluation.py, this runs ``retrieve()`` against in-memory chunks with the
hashing embedder — it diagnoses chunking and ranking, not the production
pgvector + OpenAI embeddings path.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from statistics import median

from app.services.rag.embeddings import HashingEmbedder
from app.services.rag.official.evaluation import RetrievalEvalCase, load_retrieval_eval_cases
from app.services.rag.official.loaders import load_official_chunks
from app.services.rag.official.models import RagChunk, RetrievalHit
from app.services.rag.official.retrieval import retrieve

_VISIBLE_CONTEXT_CHARS = 900


@dataclass(frozen=True)
class ChunkLengthStats:
    source_id: str
    count: int
    minimum: int
    p50: int
    p90: int
    p95: int
    maximum: int


@dataclass(frozen=True)
class RetrievalDiagnosticResult:
    case_id: str
    query: str
    candidate_rank: int | None
    final_rank: int | None
    visible_rank: int | None
    top_hits: tuple[RetrievalHit, ...]


@dataclass(frozen=True)
class RetrievalDiagnosticReport:
    total_chunks: int
    chunk_stats: tuple[ChunkLengthStats, ...]
    long_chunks: tuple[RagChunk, ...]
    results: tuple[RetrievalDiagnosticResult, ...]

    @property
    def candidate_recall_at_24(self) -> float:
        return _rate(
            result.candidate_rank is not None and result.candidate_rank <= 24
            for result in self.results
        )

    @property
    def recall_at_1(self) -> float:
        return _rate(result.final_rank == 1 for result in self.results)

    @property
    def recall_at_3(self) -> float:
        return _rate(
            result.final_rank is not None and result.final_rank <= 3 for result in self.results
        )

    @property
    def recall_at_5(self) -> float:
        return _rate(
            result.final_rank is not None and result.final_rank <= 5 for result in self.results
        )

    @property
    def visible_recall_at_5(self) -> float:
        return _rate(
            result.visible_rank is not None and result.visible_rank <= 5 for result in self.results
        )


def diagnose_retrieval(
    cases: tuple[RetrievalEvalCase, ...] | None = None,
    *,
    long_chunk_threshold: int = 3000,
) -> RetrievalDiagnosticReport:
    chunks = load_official_chunks()
    active_cases = cases or load_retrieval_eval_cases()
    return RetrievalDiagnosticReport(
        total_chunks=len(chunks),
        chunk_stats=_chunk_stats(chunks),
        long_chunks=tuple(
            sorted(
                (chunk for chunk in chunks if len(chunk.text) > long_chunk_threshold),
                key=lambda chunk: len(chunk.text),
                reverse=True,
            )
        ),
        results=tuple(_diagnose_case(case, chunks) for case in active_cases),
    )


def render_report(report: RetrievalDiagnosticReport) -> str:
    lines = [
        "=== CORPUS ===",
        f"total_chunks {report.total_chunks}",
    ]
    for stats in report.chunk_stats:
        lines.append(
            f"{stats.source_id} count {stats.count} min {stats.minimum} "
            f"p50 {stats.p50} p90 {stats.p90} p95 {stats.p95} max {stats.maximum}"
        )

    lines.extend(("", "=== LONG CHUNKS > 3000 ===", f"count {len(report.long_chunks)}"))
    for chunk in report.long_chunks[:20]:
        lines.append(
            f"{chunk.source_id} p {chunk.page_start}-{chunk.page_end} "
            f"len {len(chunk.text)} label {chunk.label}"
        )

    lines.extend(
        (
            "",
            "=== METRICS ===",
            _metric_line("candidate_recall@24", report.candidate_recall_at_24, report.results),
            _metric_line("recall@1", report.recall_at_1, report.results),
            _metric_line("recall@3", report.recall_at_3, report.results),
            _metric_line("recall@5", report.recall_at_5, report.results),
            _metric_line("visible_recall@5", report.visible_recall_at_5, report.results),
            "",
            "=== CASES ===",
        )
    )
    for result in report.results:
        lines.extend(_case_lines(result))
    return "\n".join(lines)


def _chunk_stats(chunks: tuple[RagChunk, ...]) -> tuple[ChunkLengthStats, ...]:
    grouped: dict[str, list[int]] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.source_id, []).append(len(chunk.text))

    stats: list[ChunkLengthStats] = []
    for source_id, lengths in grouped.items():
        sorted_lengths = sorted(lengths)
        stats.append(
            ChunkLengthStats(
                source_id=source_id,
                count=len(sorted_lengths),
                minimum=sorted_lengths[0],
                p50=int(median(sorted_lengths)),
                p90=_percentile(sorted_lengths, 0.90),
                p95=_percentile(sorted_lengths, 0.95),
                maximum=sorted_lengths[-1],
            )
        )
    return tuple(sorted(stats, key=lambda item: item.source_id))


def _diagnose_case(
    case: RetrievalEvalCase,
    chunks: tuple[RagChunk, ...],
) -> RetrievalDiagnosticResult:
    embedder = HashingEmbedder()
    candidate_hits = retrieve(
        case.query,
        chunks=chunks,
        embedder=embedder,
        candidate_k=200,
        final_k=200,
    )
    top_hits = retrieve(
        case.query,
        chunks=chunks,
        embedder=embedder,
        candidate_k=24,
        final_k=10,
    )
    return RetrievalDiagnosticResult(
        case_id=case.id,
        query=case.query,
        candidate_rank=_first_rank(case, candidate_hits, visible_only=False),
        final_rank=_first_rank(case, top_hits, visible_only=False),
        visible_rank=_first_rank(case, top_hits, visible_only=True),
        top_hits=tuple(top_hits[:5]),
    )


def _first_rank(
    case: RetrievalEvalCase,
    hits: list[RetrievalHit],
    *,
    visible_only: bool,
) -> int | None:
    if case.expected_no_hits:
        return None
    for rank, hit in enumerate(hits, start=1):
        if hit.chunk.id in case.relevant_chunk_ids:
            return rank
    return None


def _case_lines(result: RetrievalDiagnosticResult) -> list[str]:
    lines = [
        "",
        f"CASE {result.case_id}",
        f"query {result.query}",
        f"candidate_rank {result.candidate_rank}",
        f"final_rank {result.final_rank}",
        f"visible_rank {result.visible_rank}",
    ]
    for rank, hit in enumerate(result.top_hits, start=1):
        lines.append(
            f"  {rank}. source={hit.chunk.source_id} kw={hit.keyword_score} "
            f"score={hit.score} len={len(hit.chunk.text)} "
            f"p={hit.chunk.page_start}-{hit.chunk.page_end} label={hit.chunk.label}"
        )
    return lines


def _metric_line(
    label: str,
    value: float,
    results: tuple[RetrievalDiagnosticResult, ...],
) -> str:
    passed = round(value * len(results))
    return f"{label} {passed}/{len(results)} {value:.3f}"


def _percentile(values: list[int], percentile: float) -> int:
    index = min(int(len(values) * percentile), len(values) - 1)
    return values[index]


def _rate(values: Iterable[bool]) -> float:
    results = list(values)
    if not results:
        return 0.0
    return Counter(results)[True] / len(results)


def main() -> None:
    print(render_report(diagnose_retrieval()))


if __name__ == "__main__":
    main()
