"""End-to-end evaluation for official-source RAG.

This runner evaluates the official RAG path as retrieval followed by answer
generation. The default completer is deterministic and extractive so the
offline score tracks retrieval-to-answer wiring without requiring an OpenAI
API key. Use ``--live-generation`` when validating the live LLM answer step.
"""

from __future__ import annotations

import json
from argparse import ArgumentParser
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from app.core.config import get_settings
from app.integrations.openai import JsonCompleter, compact_prompt_text
from app.rag.embeddings import HashingEmbedder
from app.rag.official.answer import RagAnswerStatus, answer_official_question
from app.rag.official.loaders import load_official_chunks
from app.rag.official.models import RagChunk
from app.rag.official.retrieval import retrieve
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

EVAL_FIXTURE = Path(__file__).resolve().parent / "e2e_dataset.json"
_OFFLINE_ANSWER_CHARS = 850


@dataclass(frozen=True)
class OfficialRagE2EReport:
    passed: int
    total: int
    results: tuple[OfficialRagE2EResult, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def retrieval_required_citation_rate(self) -> float:
        return _rate(result.required_citations_retrieved for result in self.results)

    @property
    def answer_contract_rate(self) -> float:
        return _rate(result.answer_contract_passed for result in self.results)


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
    live_generation: bool = False,
) -> OfficialRagE2EReport:
    active_completer = complete
    if not live_generation and active_completer is None:
        active_completer = offline_extractive_completer
    if live_generation and active_completer is None and not get_settings().openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live official RAG E2E evaluation")

    active_cases = cases if cases is not None else load_e2e_eval_cases()
    chunks = load_official_chunks()
    results = tuple(
        _evaluate_case(
            case,
            chunks=chunks,
            complete=active_completer,
        )
        for case in active_cases
    )

    return OfficialRagE2EReport(
        passed=sum(result.passed for result in results),
        total=len(results),
        results=results,
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
    lines = [
        (
            f"passed={report.passed}/{report.total} "
            f"pass_rate={report.pass_rate:.3f} "
            f"retrieval_required_citations={report.retrieval_required_citation_rate:.3f} "
            f"answer_contract={report.answer_contract_rate:.3f}"
        )
    ]

    for result in report.results:
        if result.passed and not show_passing:
            continue
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"{status} {result.case_id} "
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
    complete: JsonCompleter | None,
) -> OfficialRagE2EResult:
    hits = retrieve(
        query=case.question,
        chunks=chunks,
        embedder=HashingEmbedder(),
        final_k=5,
    )
    hit_chunk_ids = tuple(hit.chunk.id for hit in hits)
    required_citations_retrieved = all(
        citation_id in hit_chunk_ids for citation_id in case.required_citation_ids
    )
    answer = answer_official_question(case.question, hits=hits, complete=complete)
    citation_ids = tuple(citation.chunk_id for citation in answer.citations)
    answer_text = _normalize(answer.answer)
    status_matched = answer.status == case.expected_status
    citation_valid = all(citation_id in hit_chunk_ids for citation_id in citation_ids)
    required_citation_covered = not case.required_citation_ids or (
        answer.status == "answered"
        and all(citation_id in citation_ids for citation_id in case.required_citation_ids)
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
            status_matched=status_matched,
            citation_valid=citation_valid,
            required_citation_covered=required_citation_covered,
            must_include_covered=must_include_covered,
            must_not_include_clean=must_not_include_clean,
            answer_text=answer.answer,
            citation_ids=citation_ids,
            answer_status=answer.status,
        ),
    )


def _notes(
    case: GenerationEvalCase,
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
        missing = sorted(set(case.required_citation_ids) - set(citation_ids))
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
        required_citation_ids=() if expected_no_hits else case.relevant_chunk_ids,
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


def _missing_term_groups(groups: tuple[tuple[str, ...], ...], text: str) -> tuple[str, ...]:
    normalized = _normalize(text)
    return tuple(
        " / ".join(group)
        for group in groups
        if not any(_normalize(term) in normalized for term in group)
    )


def _present_terms(terms: tuple[str, ...], text: str) -> tuple[str, ...]:
    normalized = _normalize(text)
    return tuple(term for term in terms if _normalize(term) in normalized)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(list[object], value))


def _string_groups(value: object) -> tuple[tuple[str, ...], ...]:
    return tuple(_string_tuple(group) for group in cast(list[object], value))


def _rate(values: Iterable[bool]) -> float:
    items = tuple(bool(value) for value in values)
    return sum(1 for item in items if item) / len(items) if items else 0.0


def _parse_args() -> tuple[Path, bool, bool]:
    parser = ArgumentParser(description="Evaluate official RAG retrieval-to-generation E2E.")
    parser.add_argument("--path", type=Path, default=EVAL_FIXTURE)
    parser.add_argument("--live-generation", action="store_true")
    parser.add_argument("--show-passing", action="store_true")
    args = parser.parse_args()
    return cast(Path, args.path), bool(args.live_generation), bool(args.show_passing)


if __name__ == "__main__":
    path, live_generation, show_passing = _parse_args()
    report = evaluate_e2e(
        load_e2e_eval_cases(path),
        live_generation=live_generation,
    )
    print(render_report(report, show_passing=show_passing))
