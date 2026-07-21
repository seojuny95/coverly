"""End-to-end evaluation for official-source RAG.

This runner evaluates the official RAG path as retrieval followed by answer
generation. Retrieval and generation modes are explicit so deterministic,
production-retrieval, and fully live results can be compared consistently.
"""

from __future__ import annotations

import json
import re
import time
from argparse import SUPPRESS, ArgumentParser
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import psycopg
from psycopg import sql

from app.core.config import get_settings
from app.integrations.openai import JsonCompleter, compact_prompt_text
from app.rag.embeddings import HashingEmbedder
from app.rag.official.answer import RagAnswerStatus, answer_official_question
from app.rag.official.loaders import load_official_chunks
from app.rag.official.models import RagChunk
from app.rag.official.retrieval import retrieve
from evals.rag.data import string_groups as _string_groups
from evals.rag.data import string_tuple as _string_tuple
from evals.rag.execution import (
    GenerationMode,
    RagEvalRunMetadata,
    RetrievalMode,
    build_run_metadata,
    content_version,
    validate_execution_modes,
)
from evals.rag.official.generation import (
    EVAL_FIXTURE as GENERATION_FIXTURE,
)
from evals.rag.official.generation import (
    GenerationDifficulty,
    GenerationEvalCase,
    GenerationProfile,
    load_generation_eval_cases,
)
from evals.rag.official.retrieval import RetrievalEvalCase, load_retrieval_eval_cases
from evals.rag.text import missing_term_groups as _missing_term_groups
from evals.rag.text import normalize_whitespace as _normalize
from evals.rag.text import present_terms as _present_terms

EVAL_FIXTURE = Path(__file__).resolve().parent / "e2e_dataset.json"
_OFFLINE_ANSWER_CHARS = 850
_LABEL_TITLE_RE = re.compile(r"\(([^)]+)\)")
FailureBucket = Literal[
    "passed",
    "retrieval_miss",
    "answerability_status_mismatch",
    "citation_not_used",
    "answer_missing_required_content",
    "forbidden_content",
    "other",
]


@dataclass(frozen=True)
class OfficialRagE2EReport:
    passed: int
    total: int
    results: tuple[OfficialRagE2EResult, ...]
    metadata: RagEvalRunMetadata

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def retrieval_required_citation_rate(self) -> float:
        return _rate(result.required_citations_retrieved for result in self.results)

    @property
    def answer_contract_rate(self) -> float:
        return _rate(result.answer_contract_passed for result in self.results)

    @property
    def failure_buckets(self) -> dict[FailureBucket, int]:
        buckets: dict[FailureBucket, int] = {}
        for result in self.results:
            bucket = result.failure_bucket
            buckets[bucket] = buckets.get(bucket, 0) + 1
        return buckets


@dataclass(frozen=True)
class OfficialRagE2EResult:
    case_id: str
    question: str
    passed: bool
    required_citations_retrieved: bool
    answer_contract_passed: bool
    status_matched: bool
    citation_valid: bool
    required_citation_covered: bool
    must_include_covered: bool
    must_not_include_clean: bool
    hit_chunk_ids: tuple[str, ...]
    answer_status: str
    citation_ids: tuple[str, ...]
    notes: tuple[str, ...]
    retrieval_latency_seconds: float
    generation_latency_seconds: float

    @property
    def failure_bucket(self) -> FailureBucket:
        if self.passed:
            return "passed"
        if not self.required_citations_retrieved:
            return "retrieval_miss"
        if not self.status_matched:
            return "answerability_status_mismatch"
        if not self.required_citation_covered:
            return "citation_not_used"
        if not self.must_include_covered:
            return "answer_missing_required_content"
        if not self.must_not_include_clean:
            return "forbidden_content"
        return "other"


def load_e2e_eval_cases(path: Path = EVAL_FIXTURE) -> tuple[GenerationEvalCase, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        selected_ids = _selected_scenario_ids(raw)
        return tuple(
            case
            for case in load_generation_eval_cases(GENERATION_FIXTURE)
            if _scenario_id(case.id) in selected_ids
        )

    config = cast(dict[str, object], raw)
    return (
        *_generation_cases_from_config(config["generation_cases"]),
        *_retrieval_cases_from_config(config["retrieval_cases"]),
        *_extra_cases_from_config(config["extra_cases"]),
    )


def evaluate_e2e(
    cases: tuple[GenerationEvalCase, ...] | None = None,
    *,
    complete: JsonCompleter | None = None,
    retrieval_mode: RetrievalMode = "offline",
    generation_mode: GenerationMode = "deterministic",
    live_generation: bool | None = None,
) -> OfficialRagE2EReport:
    if live_generation is not None:
        generation_mode = "live" if live_generation else "deterministic"
    validate_execution_modes(retrieval_mode, generation_mode)
    active_completer = complete
    if generation_mode == "deterministic" and active_completer is None:
        active_completer = offline_extractive_completer
    if (
        generation_mode == "live"
        and active_completer is None
        and not get_settings().openai_api_key.get_secret_value()
    ):
        raise RuntimeError("OPENAI_API_KEY is required for live official RAG E2E evaluation")

    active_cases = cases if cases is not None else load_e2e_eval_cases()
    chunks = load_official_chunks()
    chunks_by_id = {chunk.id: chunk for chunk in chunks}
    settings = get_settings()
    corpus_version = _official_corpus_version(chunks)
    index_version = (
        f"in-memory:{corpus_version}"
        if retrieval_mode == "offline"
        else _production_index_version(
            database_url=settings.database_url.get_secret_value(),
            table_name=settings.rag_pg_table,
        )
    )
    executed_at = datetime.now(UTC)
    results = tuple(
        _evaluate_case(
            case,
            chunks=chunks,
            chunks_by_id=chunks_by_id,
            complete=active_completer,
            retrieval_mode=retrieval_mode,
        )
        for case in active_cases
    )

    if retrieval_mode == "production":
        final_index_version = _production_index_version(
            database_url=settings.database_url.get_secret_value(),
            table_name=settings.rag_pg_table,
        )
        if final_index_version != index_version:
            raise RuntimeError(
                "official RAG index changed during E2E evaluation: "
                f"{index_version} -> {final_index_version}"
            )

    return OfficialRagE2EReport(
        passed=sum(result.passed for result in results),
        total=len(results),
        results=results,
        metadata=build_run_metadata(
            retrieval_mode=retrieval_mode,
            generation_mode=generation_mode,
            retrieval_model=(
                "hashing-embedder-v1"
                if retrieval_mode == "offline"
                else f"{settings.openai_embedding_model}+{settings.openai_model}-reranker"
            ),
            generation_model=(
                "injected-completer"
                if complete is not None and complete is not offline_extractive_completer
                else (
                    "offline-extractive-v1"
                    if generation_mode == "deterministic"
                    else settings.openai_model
                )
            ),
            corpus_version=corpus_version,
            index_version=index_version,
            retrieval_latencies=tuple(result.retrieval_latency_seconds for result in results),
            generation_latencies=tuple(result.generation_latency_seconds for result in results),
            executed_at=executed_at,
        ),
    )


def offline_extractive_completer(_: str, user: str) -> dict[str, object]:
    """Return a grounded extractive draft from retrieved excerpts."""

    payload = json.loads(user)
    excerpts = cast(list[dict[str, object]], payload.get("excerpts", []))
    if not excerpts:
        return {
            "answer": "공식 자료에서 답변 근거를 찾지 못했습니다.",
            "citation_ids": [],
            "missing_context": ["관련 공식 근거"],
        }

    citation_ids = [str(excerpt.get("id", "")) for excerpt in excerpts if excerpt.get("id")]
    answer_parts = [
        compact_prompt_text(str(excerpt.get("text", "")), 260)
        for excerpt in excerpts
        if excerpt.get("text")
    ]
    answer = "\n\n".join(answer_parts)

    return {
        "answer": compact_prompt_text(answer, _OFFLINE_ANSWER_CHARS),
        "citation_ids": citation_ids,
        "missing_context": [],
    }


def render_report(report: OfficialRagE2EReport, *, show_passing: bool = False) -> str:
    metadata = report.metadata
    lines = [
        (
            f"retrieval_mode={metadata.retrieval_mode} "
            f"generation_mode={metadata.generation_mode} "
            f"retrieval_model={metadata.retrieval_model} "
            f"generation_model={metadata.generation_model}"
        ),
        (
            f"executed_at={metadata.executed_at.isoformat()} "
            f"corpus_version={metadata.corpus_version} "
            f"index_version={metadata.index_version}"
        ),
        (
            f"passed={report.passed}/{report.total} "
            f"pass_rate={report.pass_rate:.3f} "
            f"retrieval_required_citations={report.retrieval_required_citation_rate:.3f} "
            f"answer_contract={report.answer_contract_rate:.3f}"
        ),
        (
            f"latency_avg_s retrieval={metadata.retrieval_average_latency_seconds:.3f} "
            f"generation={metadata.generation_average_latency_seconds:.3f} "
            f"total={metadata.total_average_latency_seconds:.3f}"
        ),
        (
            f"latency_p95_s retrieval={metadata.retrieval_p95_latency_seconds:.3f} "
            f"generation={metadata.generation_p95_latency_seconds:.3f} "
            f"total={metadata.total_p95_latency_seconds:.3f}"
        ),
    ]
    failed_buckets = {
        bucket: count
        for bucket, count in report.failure_buckets.items()
        if bucket != "passed" and count
    }
    if failed_buckets:
        lines.append(
            "failure_buckets="
            + ", ".join(f"{bucket}:{count}" for bucket, count in failed_buckets.items())
        )

    for result in report.results:
        if result.passed and not show_passing:
            continue
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"{status} {result.case_id} "
            f"bucket={result.failure_bucket} "
            f"retrieved_required={result.required_citations_retrieved} "
            f"status={result.answer_status}"
        )
        lines.append(f"  hits: {', '.join(result.hit_chunk_ids)}")
        for note in result.notes:
            lines.append(f"  - {note}")

    return "\n".join(lines)


def _evaluate_case(
    case: GenerationEvalCase,
    *,
    chunks: tuple[RagChunk, ...],
    chunks_by_id: dict[str, RagChunk],
    complete: JsonCompleter | None,
    retrieval_mode: RetrievalMode,
) -> OfficialRagE2EResult:
    retrieval_started = time.perf_counter()
    if retrieval_mode == "offline":
        hits = retrieve(
            query=case.question,
            chunks=chunks,
            embedder=HashingEmbedder(),
            final_k=5,
        )
    else:
        hits = retrieve(query=case.question, final_k=5)
    retrieval_latency = time.perf_counter() - retrieval_started
    hit_chunk_ids = tuple(hit.chunk.id for hit in hits)
    required_citation_groups = _required_citation_groups(case, chunks_by_id)
    required_citations_retrieved = not required_citation_groups or all(
        any(citation_id in hit_chunk_ids for citation_id in group)
        for group in required_citation_groups
    )
    generation_started = time.perf_counter()
    answer = answer_official_question(case.question, hits=hits, complete=complete)
    generation_latency = time.perf_counter() - generation_started
    citation_ids = tuple(citation.chunk_id for citation in answer.citations)
    answer_text = _normalize(answer.answer)
    status_matched = answer.status == case.expected_status
    citation_valid = all(citation_id in hit_chunk_ids for citation_id in citation_ids)
    required_citation_covered = not required_citation_groups or (
        answer.status == "answered"
        and all(
            any(citation_id in citation_ids for citation_id in group)
            for group in required_citation_groups
        )
    )
    must_include_covered = all(
        any(_normalize(term) in answer_text for term in group) for group in case.must_include_groups
    )
    must_not_include_clean = all(
        _normalize(term) not in answer_text for term in case.must_not_include
    )
    answer_contract_passed = (
        status_matched
        and citation_valid
        and required_citation_covered
        and must_include_covered
        and must_not_include_clean
    )
    passed = required_citations_retrieved and answer_contract_passed

    return OfficialRagE2EResult(
        case_id=case.id,
        question=case.question,
        passed=passed,
        required_citations_retrieved=required_citations_retrieved,
        answer_contract_passed=answer_contract_passed,
        status_matched=status_matched,
        citation_valid=citation_valid,
        required_citation_covered=required_citation_covered,
        must_include_covered=must_include_covered,
        must_not_include_clean=must_not_include_clean,
        hit_chunk_ids=hit_chunk_ids,
        answer_status=answer.status,
        citation_ids=citation_ids,
        notes=_notes(
            case,
            chunks_by_id,
            status_matched=status_matched,
            citation_valid=citation_valid,
            required_citation_covered=required_citation_covered,
            must_include_covered=must_include_covered,
            must_not_include_clean=must_not_include_clean,
            answer_text=answer.answer,
            citation_ids=citation_ids,
            answer_status=answer.status,
        ),
        retrieval_latency_seconds=retrieval_latency,
        generation_latency_seconds=generation_latency,
    )


def _official_corpus_version(chunks: tuple[RagChunk, ...]) -> str:
    return content_version(
        *(
            f"{chunk.id}\n{chunk.source_id}\n{chunk.version_label}\n{chunk.text}"
            for chunk in sorted(chunks, key=lambda item: item.id)
        )
    )


def _production_index_version(*, database_url: str, table_name: str) -> str:
    if not database_url:
        return f"pgvector:{table_name}:unavailable"
    if re.fullmatch(r"[a-z_][a-z0-9_]*", table_name) is None:
        raise ValueError("official RAG table name must be a safe SQL identifier")

    physical_table_name = f"data_{table_name}"
    statement = sql.SQL("SELECT text, metadata_ FROM {} ORDER BY node_id").format(
        sql.Identifier(physical_table_name)
    )
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(statement).fetchall()
    nodes = tuple(
        (str(row[0]), json.loads(str(cast(dict[str, object], row[1])["_node_content"])))
        for row in rows
    )
    index_version = content_version(
        *(
            f"{node['id_']}\n{cast(dict[str, object], node['metadata'])['source_id']}\n"
            f"{cast(dict[str, object], node['metadata']).get('version_label')}\n{text}"
            for text, node in nodes
        )
    )
    return f"pgvector:{table_name}:{index_version}"


def _notes(
    case: GenerationEvalCase,
    chunks_by_id: dict[str, RagChunk],
    *,
    status_matched: bool,
    citation_valid: bool,
    required_citation_covered: bool,
    must_include_covered: bool,
    must_not_include_clean: bool,
    answer_text: str,
    citation_ids: tuple[str, ...],
    answer_status: str,
) -> tuple[str, ...]:
    notes: list[str] = []
    if not status_matched:
        notes.append(f"expected status {case.expected_status}, got {answer_status}")
    if not citation_valid:
        notes.append("answer cited chunks that were not retrieved")
    if not required_citation_covered:
        missing = _missing_citation_groups(case, chunks_by_id, citation_ids)
        notes.append(f"missing required citation ids: {', '.join(missing)}")
    if not must_include_covered:
        missing_groups = _missing_term_groups(case.must_include_groups, answer_text)
        notes.append(f"missing required answer groups: {', '.join(missing_groups)}")
    if not must_not_include_clean:
        present = _present_terms(case.must_not_include, answer_text)
        notes.append(f"forbidden answer terms present: {', '.join(present)}")
    return tuple(notes)


def _generation_cases_from_config(raw: object) -> tuple[GenerationEvalCase, ...]:
    config = cast(dict[str, object], raw)
    selected_ids = _selected_scenario_ids_from_config(config["include"])
    return tuple(
        case
        for case in load_generation_eval_cases(GENERATION_FIXTURE)
        if _scenario_id(case.id) in selected_ids
    )


def _retrieval_cases_from_config(raw: object) -> tuple[GenerationEvalCase, ...]:
    config = cast(dict[str, object], raw)
    retrieval_cases = load_retrieval_eval_cases()
    selected_ids = _selected_retrieval_case_ids(config["include"], retrieval_cases)
    return tuple(
        _generation_case_from_retrieval_case(case)
        for case in retrieval_cases
        if case.id in selected_ids
    )


def _extra_cases_from_config(raw: object) -> tuple[GenerationEvalCase, ...]:
    return tuple(
        _extra_case_from_json(cast(dict[str, object], item)) for item in cast(list[object], raw)
    )


def _generation_case_from_retrieval_case(case: RetrievalEvalCase) -> GenerationEvalCase:
    expected_no_hits = case.expected_no_hits
    must_include_groups = tuple(
        (term,) for accepted in case.accepted_evidence for term in accepted.required_terms
    )
    return GenerationEvalCase(
        id=f"retrieval__{case.id}",
        question=case.query,
        hit_chunk_ids=case.relevant_chunk_ids,
        expected_status="no_evidence" if expected_no_hits else "answered",
        must_include_groups=() if expected_no_hits else must_include_groups,
        must_not_include=(
            "가입하세요",
            "무조건 지급",
            "반드시 보장",
            "공식자료에서 확인했습니다" if expected_no_hits else "상품을 추천합니다",
        ),
        required_citation_ids=(),
        required_citation_groups=() if expected_no_hits else (case.relevant_chunk_ids,),
        expected_missing_context_terms=(),
        profile=case.profile,
        difficulty=case.difficulty,
    )


def _extra_case_from_json(raw: dict[str, object]) -> GenerationEvalCase:
    return GenerationEvalCase(
        id=str(raw["id"]),
        question=str(raw["question"]),
        hit_chunk_ids=_string_tuple(raw["hit_chunk_ids"]),
        expected_status=cast(RagAnswerStatus, str(raw["expected_status"])),
        must_include_groups=_string_groups(raw["must_include_groups"]),
        must_not_include=_string_tuple(raw["must_not_include"]),
        required_citation_ids=_string_tuple(raw["required_citation_ids"]),
        required_citation_groups=tuple(
            (citation_id,) for citation_id in _string_tuple(raw["required_citation_ids"])
        ),
        expected_missing_context_terms=_string_tuple(raw["expected_missing_context_terms"]),
        profile=cast(GenerationProfile, str(raw.get("profile", "out_of_scope"))),
        difficulty=cast(GenerationDifficulty, str(raw.get("difficulty", "hard"))),
    )


def _selected_scenario_ids(raw_cases: list[object]) -> set[str]:
    return {str(cast(dict[str, object], item)["id"]) for item in raw_cases}


def _selected_scenario_ids_from_config(include: object) -> set[str]:
    if include == "all":
        return {_scenario_id(case.id) for case in load_generation_eval_cases(GENERATION_FIXTURE)}
    raw_cases = cast(list[dict[str, object]], include)
    return {str(item["id"]) for item in raw_cases}


def _selected_retrieval_case_ids(include: object, cases: tuple[RetrievalEvalCase, ...]) -> set[str]:
    if include == "all":
        return {case.id for case in cases}
    return set(_string_tuple(include))


def _scenario_id(case_id: str) -> str:
    return case_id.split("__q", maxsplit=1)[0]


def _required_citation_groups(
    case: GenerationEvalCase,
    chunks_by_id: dict[str, RagChunk],
) -> tuple[tuple[str, ...], ...]:
    groups = _base_required_citation_groups(case)
    return tuple(
        _expand_equivalent_standard_clause_citations(group, chunks_by_id) for group in groups
    )


def _missing_citation_groups(
    case: GenerationEvalCase,
    chunks_by_id: dict[str, RagChunk],
    citation_ids: tuple[str, ...],
) -> tuple[str, ...]:
    original_groups = _base_required_citation_groups(case)
    expanded_groups = _required_citation_groups(case, chunks_by_id)
    return tuple(
        " / ".join(original)
        for original, expanded in zip(original_groups, expanded_groups, strict=True)
        if not any(citation_id in citation_ids for citation_id in expanded)
    )


def _expand_equivalent_standard_clause_citations(
    citation_ids: tuple[str, ...],
    chunks_by_id: dict[str, RagChunk],
) -> tuple[str, ...]:
    expanded = list(citation_ids)
    for citation_id in citation_ids:
        chunk = chunks_by_id.get(citation_id)
        if chunk is None or chunk.source_category != "standard_clause":
            continue
        label_title = _label_title(chunk.label)
        if not label_title:
            continue
        for candidate in chunks_by_id.values():
            if candidate.source_category != "standard_clause":
                continue
            if candidate.source_id != chunk.source_id:
                continue
            if _label_title(candidate.label) == label_title:
                expanded.append(candidate.id)
    return tuple(dict.fromkeys(expanded))


def _base_required_citation_groups(case: GenerationEvalCase) -> tuple[tuple[str, ...], ...]:
    if case.required_citation_groups:
        return case.required_citation_groups
    return tuple((citation_id,) for citation_id in case.required_citation_ids)


def _label_title(label: str | None) -> str:
    if not label:
        return ""
    match = _LABEL_TITLE_RE.search(label)
    if match is None:
        return ""
    return _normalize(match.group(1)).replace(" ", "")


def _rate(values: Iterable[bool]) -> float:
    items = tuple(bool(value) for value in values)
    return sum(1 for item in items if item) / len(items) if items else 0.0


def _parse_args() -> tuple[Path, RetrievalMode, GenerationMode, bool]:
    parser = ArgumentParser(description="Evaluate official RAG retrieval-to-generation E2E.")
    parser.add_argument("--path", type=Path, default=EVAL_FIXTURE)
    parser.add_argument("--retrieval-mode", choices=("offline", "production"), default="offline")
    parser.add_argument(
        "--generation-mode", choices=("deterministic", "live"), default="deterministic"
    )
    parser.add_argument("--live-generation", action="store_true", help=SUPPRESS)
    parser.add_argument("--show-passing", action="store_true")
    args = parser.parse_args()
    return (
        cast(Path, args.path),
        cast(RetrievalMode, args.retrieval_mode),
        "live" if args.live_generation else cast(GenerationMode, args.generation_mode),
        bool(args.show_passing),
    )


if __name__ == "__main__":
    path, retrieval_mode, generation_mode, show_passing = _parse_args()
    report = evaluate_e2e(
        load_e2e_eval_cases(path),
        retrieval_mode=retrieval_mode,
        generation_mode=generation_mode,
    )
    print(render_report(report, show_passing=show_passing))
