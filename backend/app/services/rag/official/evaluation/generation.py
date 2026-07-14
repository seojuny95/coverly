"""Fixed-context evaluation for official-source RAG generation.

The evaluator intentionally keeps the method simple: load hand-labeled cases,
run the answer pipeline with fixed retrieved chunks, and score the returned
answer against explicit contract checks. It does not use semantic similarity,
embedding-based grading, or another LLM as a judge.
"""

from __future__ import annotations

import json
import re
from argparse import ArgumentParser
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from app.services.llm import JsonCompleter
from app.services.rag.official.answer import RagAnswer, RagAnswerStatus, answer_official_question
from app.services.rag.official.loaders import load_official_chunks
from app.services.rag.official.models import RagChunk, RetrievalHit
from app.settings import get_settings

EVAL_FIXTURE = Path(__file__).resolve().parent / "generation_dataset.json"

GenerationCheckName = Literal[
    "status",
    "citation_validity",
    "required_citations",
    "must_include",
    "must_not_include",
    "missing_context",
    "numeric_grounding",
]

GenerationProfile = Literal["term_explain", "claim_check", "consumer_protection", "out_of_scope"]
GenerationDifficulty = Literal["easy", "medium", "hard"]

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])\d+(?:[.,]\d+)?(?![A-Za-z0-9])")
_BULLET_NUMBER_RE = re.compile(r"(?m)^\s*\d+[.)]\s*")


@dataclass(frozen=True)
class GenerationEvalCase:
    id: str
    question: str
    hit_chunk_ids: tuple[str, ...]
    expected_status: RagAnswerStatus
    must_include_groups: tuple[tuple[str, ...], ...]
    must_not_include: tuple[str, ...]
    required_citation_ids: tuple[str, ...]
    expected_missing_context_terms: tuple[str, ...]
    profile: GenerationProfile = "term_explain"
    difficulty: GenerationDifficulty = "medium"


@dataclass(frozen=True)
class GenerationEvalResult:
    case_id: str
    question: str
    passed: bool
    status_matched: bool
    citation_valid: bool
    required_citation_covered: bool
    must_include_covered: bool
    must_not_include_clean: bool
    missing_context_covered: bool
    numeric_grounded: bool
    failed_checks: tuple[GenerationCheckName, ...]
    notes: tuple[str, ...]
    answer_status: RagAnswerStatus
    answer: str
    citation_ids: tuple[str, ...]
    missing_context: tuple[str, ...]


@dataclass(frozen=True)
class GenerationEvalReport:
    passed: int
    total: int
    results: tuple[GenerationEvalResult, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def status_match_rate(self) -> float:
        return _rate(result.status_matched for result in self.results)

    @property
    def citation_valid_rate(self) -> float:
        return _rate(result.citation_valid for result in self.results)

    @property
    def required_citation_coverage(self) -> float:
        return _rate(result.required_citation_covered for result in self.results)

    @property
    def must_include_coverage(self) -> float:
        return _rate(result.must_include_covered for result in self.results)

    @property
    def must_not_include_clean_rate(self) -> float:
        return _rate(result.must_not_include_clean for result in self.results)

    @property
    def missing_context_coverage(self) -> float:
        return _rate(result.missing_context_covered for result in self.results)

    @property
    def numeric_grounding_rate(self) -> float:
        return _rate(result.numeric_grounded for result in self.results)


def load_generation_eval_cases(path: Path = EVAL_FIXTURE) -> tuple[GenerationEvalCase, ...]:
    raw_scenarios = cast(list[dict[str, object]], json.loads(path.read_text(encoding="utf-8")))
    cases: list[GenerationEvalCase] = []
    for raw in raw_scenarios:
        questions = _string_tuple(raw["questions"])
        for index, question in enumerate(questions, start=1):
            cases.append(_case_from_json(raw, question=question, index=index))
    return tuple(cases)


def evaluate_generation(
    cases: tuple[GenerationEvalCase, ...] | None = None,
    *,
    complete: JsonCompleter | None = None,
) -> GenerationEvalReport:
    if complete is None and not get_settings().openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live generation evaluation")

    active_cases = cases if cases is not None else load_generation_eval_cases()
    chunks_by_id = {chunk.id: chunk for chunk in load_official_chunks()}
    results = tuple(
        _evaluate_case(
            case,
            _answer_case(case, chunks_by_id, complete=complete),
            chunks_by_id,
        )
        for case in active_cases
    )

    return GenerationEvalReport(
        passed=sum(1 for result in results if result.passed),
        total=len(results),
        results=results,
    )


def render_report(report: GenerationEvalReport, *, show_passing: bool = False) -> str:
    lines = [
        (
            f"passed={report.passed}/{report.total} "
            f"pass_rate={report.pass_rate:.3f} "
            f"status={report.status_match_rate:.3f} "
            f"citations={report.citation_valid_rate:.3f} "
            f"required_citations={report.required_citation_coverage:.3f} "
            f"must_include={report.must_include_coverage:.3f} "
            f"must_not_include={report.must_not_include_clean_rate:.3f} "
            f"missing_context={report.missing_context_coverage:.3f} "
            f"numeric_grounding={report.numeric_grounding_rate:.3f}"
        )
    ]

    for result in report.results:
        if result.passed and not show_passing:
            continue
        status = "PASS" if result.passed else "FAIL"
        lines.append(f"{status} {result.case_id} status={result.answer_status}")
        for note in result.notes:
            lines.append(f"  - {note}")
        if result.answer:
            lines.append(f"  answer: {result.answer}")
        if result.missing_context:
            lines.append(f"  missing_context: {', '.join(result.missing_context)}")
        if result.citation_ids:
            lines.append(f"  citations: {', '.join(result.citation_ids)}")

    return "\n".join(lines)


def _case_from_json(raw: dict[str, object], *, question: str, index: int) -> GenerationEvalCase:
    expected_status = str(raw["expected_status"])
    if expected_status not in {"answered", "no_evidence", "filtered"}:
        raise ValueError(f"unknown expected_status: {expected_status}")

    return GenerationEvalCase(
        id=f"{raw['id']}__q{index}",
        question=question,
        hit_chunk_ids=_string_tuple(raw["hit_chunk_ids"]),
        expected_status=cast(RagAnswerStatus, expected_status),
        must_include_groups=_string_groups(raw["must_include_groups"]),
        must_not_include=_string_tuple(raw["must_not_include"]),
        required_citation_ids=_string_tuple(raw["required_citation_ids"]),
        expected_missing_context_terms=_string_tuple(raw["expected_missing_context_terms"]),
        profile=_generation_profile(raw["profile"]),
        difficulty=_generation_difficulty(raw["difficulty"]),
    )


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(list[object], value))


def _string_groups(value: object) -> tuple[tuple[str, ...], ...]:
    return tuple(_string_tuple(group) for group in cast(list[object], value))


def _generation_profile(value: object) -> GenerationProfile:
    profile = str(value)
    if profile not in {"term_explain", "claim_check", "consumer_protection", "out_of_scope"}:
        raise ValueError(f"unknown generation profile: {profile}")
    return cast(GenerationProfile, profile)


def _generation_difficulty(value: object) -> GenerationDifficulty:
    difficulty = str(value)
    if difficulty not in {"easy", "medium", "hard"}:
        raise ValueError(f"unknown generation difficulty: {difficulty}")
    return cast(GenerationDifficulty, difficulty)


def _answer_case(
    case: GenerationEvalCase,
    chunks_by_id: dict[str, RagChunk],
    *,
    complete: JsonCompleter | None,
) -> RagAnswer:
    hits = [_hit_for_chunk(chunks_by_id[chunk_id]) for chunk_id in case.hit_chunk_ids]
    return answer_official_question(case.question, hits=hits, complete=complete)


def _hit_for_chunk(chunk: RagChunk) -> RetrievalHit:
    return RetrievalHit(chunk=chunk, score=1.0, keyword_score=1.0, vector_score=1.0)


def _evaluate_case(
    case: GenerationEvalCase,
    answer: RagAnswer,
    chunks_by_id: dict[str, RagChunk],
) -> GenerationEvalResult:
    hit_ids = set(case.hit_chunk_ids)
    citation_ids = tuple(citation.chunk_id for citation in answer.citations)
    answer_text = _normalize(answer.answer)
    missing_context_terms = tuple(
        _normalize_missing_context_term(item) for item in answer.missing_context
    )

    status_matched = answer.status == case.expected_status
    citation_valid = all(citation_id in hit_ids for citation_id in citation_ids)
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
    missing_context_covered = all(
        _normalize_missing_context_term(term) in missing_context_terms
        for term in case.expected_missing_context_terms
    )
    numeric_grounded = _numbers_are_grounded(case.question, answer, chunks_by_id)

    checks: tuple[tuple[GenerationCheckName, bool], ...] = (
        ("status", status_matched),
        ("citation_validity", citation_valid),
        ("required_citations", required_citation_covered),
        ("must_include", must_include_covered),
        ("must_not_include", must_not_include_clean),
        ("missing_context", missing_context_covered),
        ("numeric_grounding", numeric_grounded),
    )
    failed_checks = tuple(name for name, passed in checks if not passed)

    return GenerationEvalResult(
        case_id=case.id,
        question=case.question,
        passed=not failed_checks,
        status_matched=status_matched,
        citation_valid=citation_valid,
        required_citation_covered=required_citation_covered,
        must_include_covered=must_include_covered,
        must_not_include_clean=must_not_include_clean,
        missing_context_covered=missing_context_covered,
        numeric_grounded=numeric_grounded,
        failed_checks=failed_checks,
        notes=_notes(case, answer, failed_checks, citation_ids),
        answer_status=answer.status,
        answer=answer.answer,
        citation_ids=citation_ids,
        missing_context=answer.missing_context,
    )


def _notes(
    case: GenerationEvalCase,
    answer: RagAnswer,
    failed_checks: tuple[GenerationCheckName, ...],
    citation_ids: tuple[str, ...],
) -> tuple[str, ...]:
    notes: list[str] = []
    if "status" in failed_checks:
        notes.append(f"expected status {case.expected_status}, got {answer.status}")
    if "citation_validity" in failed_checks:
        invalid = sorted(set(citation_ids) - set(case.hit_chunk_ids))
        notes.append(f"invalid citation ids: {', '.join(invalid)}")
    if "required_citations" in failed_checks:
        missing_citations = sorted(set(case.required_citation_ids) - set(citation_ids))
        notes.append(f"missing required citation ids: {', '.join(missing_citations)}")
    if "must_include" in failed_checks:
        missing_answer_groups = _missing_term_groups(case.must_include_groups, answer.answer)
        notes.append(f"missing required answer groups: {', '.join(missing_answer_groups)}")
    if "must_not_include" in failed_checks:
        present = _present_terms(case.must_not_include, answer.answer)
        notes.append(f"forbidden answer terms present: {', '.join(present)}")
    if "missing_context" in failed_checks:
        missing_context_terms = _missing_terms(
            case.expected_missing_context_terms,
            answer.missing_context,
            normalize=_normalize_missing_context_term,
        )
        notes.append(f"missing expected missing_context terms: {', '.join(missing_context_terms)}")
    if "numeric_grounding" in failed_checks:
        notes.append("answer contains a number that is absent from the question and cited evidence")
    return tuple(notes)


def _numbers_are_grounded(
    question: str,
    answer: RagAnswer,
    chunks_by_id: dict[str, RagChunk],
) -> bool:
    answer_without_bullet_numbers = _BULLET_NUMBER_RE.sub("", answer.answer)
    answer_numbers = set(_NUMBER_RE.findall(answer_without_bullet_numbers))
    if not answer_numbers:
        return True

    grounded_text = "\n".join(
        [
            question,
            *(
                "\n".join(
                    (
                        citation.source_title,
                        citation.citation_label,
                        chunks_by_id[citation.chunk_id].text,
                    )
                )
                for citation in answer.citations
                if citation.chunk_id in chunks_by_id
            ),
        ]
    )
    grounded_numbers = set(_NUMBER_RE.findall(grounded_text))
    return answer_numbers.issubset(grounded_numbers)


def _missing_terms(
    terms: tuple[str, ...],
    actual_terms: tuple[str, ...],
    *,
    normalize: Callable[[str], str] | None = None,
) -> tuple[str, ...]:
    normalizer = normalize or _normalize
    normalized_actual_terms = tuple(normalizer(term) for term in actual_terms)
    return tuple(term for term in terms if normalizer(term) not in normalized_actual_terms)


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


def _normalize_missing_context_term(text: str) -> str:
    return _normalize(text).replace(" ", "")


def _rate(values: Iterable[bool]) -> float:
    items = tuple(bool(value) for value in values)
    return sum(1 for item in items if item) / len(items) if items else 0.0


def _parse_args() -> tuple[Path, bool]:
    parser = ArgumentParser(description="Evaluate official RAG generation with fixed context.")
    parser.add_argument("--path", type=Path, default=EVAL_FIXTURE)
    parser.add_argument("--show-passing", action="store_true")
    args = parser.parse_args()
    return cast(Path, args.path), bool(args.show_passing)


if __name__ == "__main__":
    path, show_passing = _parse_args()
    report = evaluate_generation(load_generation_eval_cases(path))
    print(render_report(report, show_passing=show_passing))
