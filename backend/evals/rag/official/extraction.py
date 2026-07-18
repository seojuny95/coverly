"""Extraction evaluation for official-source RAG chunks.

This checks the step before retrieval: whether downloaded official PDFs/XML
are loaded into stable, citation-ready chunks with the expected metadata and
text. It intentionally does not embed, search, or generate answers.
"""

from __future__ import annotations

import json
import re
from argparse import ArgumentParser
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from app.rag.official.loaders import load_official_chunks
from app.rag.official.models import RagChunk, chunk_embedding_text
from evals.rag.data import string_tuple as _string_tuple

EVAL_FIXTURE = Path(__file__).resolve().parent / "extraction_dataset.json"
ExtractionCaseType = Literal["curated", "broad_regression"]


@dataclass(frozen=True)
class ExtractionEvalCase:
    id: str
    case_type: ExtractionCaseType
    source_id: str
    chunk_id: str | None
    expected_source_category: str
    expected_label: str
    expected_citation_contains: tuple[str, ...]
    expected_page_start: int
    expected_page_end: int
    must_include: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionEvalResult:
    case_id: str
    case_type: ExtractionCaseType
    passed: bool
    chunk_found: bool
    metadata_matched: bool
    citation_matched: bool
    text_covered: bool
    failed_checks: tuple[str, ...]


@dataclass(frozen=True)
class ExtractionEvalReport:
    passed: int
    total: int
    results: tuple[ExtractionEvalResult, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def chunk_found_rate(self) -> float:
        return _rate(result.chunk_found for result in self.results)

    @property
    def metadata_match_rate(self) -> float:
        return _rate(result.metadata_matched for result in self.results)

    @property
    def citation_match_rate(self) -> float:
        return _rate(result.citation_matched for result in self.results)

    @property
    def text_coverage_rate(self) -> float:
        return _rate(result.text_covered for result in self.results)

    @property
    def curated_pass_rate(self) -> float:
        return _pass_rate_for_type(self.results, "curated")

    @property
    def broad_regression_pass_rate(self) -> float:
        return _pass_rate_for_type(self.results, "broad_regression")


def load_extraction_eval_cases(path: Path = EVAL_FIXTURE) -> tuple[ExtractionEvalCase, ...]:
    raw_cases = cast(list[dict[str, object]], json.loads(path.read_text(encoding="utf-8")))
    return tuple(_case_from_json(raw) for raw in raw_cases)


def evaluate_extraction(
    cases: tuple[ExtractionEvalCase, ...] | None = None,
    *,
    chunks: tuple[RagChunk, ...] | None = None,
) -> ExtractionEvalReport:
    active_cases = cases if cases is not None else load_extraction_eval_cases()
    active_chunks = chunks if chunks is not None else load_official_chunks()
    chunks_by_id = {chunk.id: chunk for chunk in active_chunks}
    results = tuple(
        _evaluate_case(case, _chunk_for_case(case, active_chunks, chunks_by_id))
        for case in active_cases
    )
    return ExtractionEvalReport(
        passed=sum(result.passed for result in results),
        total=len(results),
        results=results,
    )


def render_report(report: ExtractionEvalReport, *, show_passing: bool = False) -> str:
    lines = [
        (
            f"passed={report.passed}/{report.total} "
            f"pass_rate={report.pass_rate:.3f} "
            f"chunk_found={report.chunk_found_rate:.3f} "
            f"metadata={report.metadata_match_rate:.3f} "
            f"citation={report.citation_match_rate:.3f} "
            f"text={report.text_coverage_rate:.3f} "
            f"curated={report.curated_pass_rate:.3f} "
            f"broad={report.broad_regression_pass_rate:.3f}"
        )
    ]
    for result in report.results:
        if result.passed and not show_passing:
            continue
        status = "PASS" if result.passed else "FAIL"
        checks = ", ".join(result.failed_checks) if result.failed_checks else "-"
        lines.append(f"{status} {result.case_id} failed_checks={checks}")
    return "\n".join(lines)


def _case_from_json(raw: dict[str, object]) -> ExtractionEvalCase:
    return ExtractionEvalCase(
        id=str(raw["id"]),
        case_type=_case_type(raw.get("case_type", "broad_regression")),
        source_id=str(raw["source_id"]),
        chunk_id=str(raw["chunk_id"]) if raw.get("chunk_id") is not None else None,
        expected_source_category=str(raw["expected_source_category"]),
        expected_label=str(raw["expected_label"]),
        expected_citation_contains=_string_tuple(raw["expected_citation_contains"]),
        expected_page_start=_int_value(raw["expected_page_start"]),
        expected_page_end=_int_value(raw["expected_page_end"]),
        must_include=_string_tuple(raw["must_include"]),
    )


def _evaluate_case(case: ExtractionEvalCase, chunk: RagChunk | None) -> ExtractionEvalResult:
    if chunk is None:
        return ExtractionEvalResult(
            case_id=case.id,
            case_type=case.case_type,
            passed=False,
            chunk_found=False,
            metadata_matched=False,
            citation_matched=False,
            text_covered=False,
            failed_checks=("chunk_found",),
        )

    metadata_matched = (
        chunk.source_id == case.source_id
        and chunk.source_category == case.expected_source_category
        and chunk.label == case.expected_label
        and chunk.page_start == case.expected_page_start
        and chunk.page_end == case.expected_page_end
    )
    citation = chunk.citation_label or ""
    citation_matched = all(
        _contains_normalized(citation, term) for term in case.expected_citation_contains
    )
    text_covered = all(
        _contains_normalized(chunk_embedding_text(chunk), term) for term in case.must_include
    )
    failed_checks = tuple(
        check
        for check, passed in (
            ("metadata", metadata_matched),
            ("citation", citation_matched),
            ("text", text_covered),
        )
        if not passed
    )

    return ExtractionEvalResult(
        case_id=case.id,
        case_type=case.case_type,
        passed=metadata_matched and citation_matched and text_covered,
        chunk_found=True,
        metadata_matched=metadata_matched,
        citation_matched=citation_matched,
        text_covered=text_covered,
        failed_checks=failed_checks,
    )


def _chunk_for_case(
    case: ExtractionEvalCase,
    chunks: tuple[RagChunk, ...],
    chunks_by_id: dict[str, RagChunk],
) -> RagChunk | None:
    if case.chunk_id is not None:
        return chunks_by_id.get(case.chunk_id)
    matches = [
        chunk
        for chunk in chunks
        if chunk.source_id == case.source_id
        and chunk.source_category == case.expected_source_category
        and chunk.label == case.expected_label
        and case.expected_page_start <= chunk.page_start
        and chunk.page_end <= case.expected_page_end
        and all(
            _contains_normalized(chunk_embedding_text(chunk), term) for term in case.must_include
        )
    ]
    if not matches:
        return None
    return matches[0]


def _int_value(value: object) -> int:
    if not isinstance(value, int):
        raise ValueError(f"expected int value: {value!r}")
    return value


def _case_type(value: object) -> ExtractionCaseType:
    case_type = str(value)
    if case_type not in {"curated", "broad_regression"}:
        raise ValueError(f"unknown extraction case_type: {case_type}")
    return cast(ExtractionCaseType, case_type)


def _contains_normalized(text: str, term: str) -> bool:
    return _normalize_text(term) in _normalize_text(text)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _rate(values: Iterable[bool]) -> float:
    items = tuple(bool(value) for value in values)
    return sum(items) / len(items) if items else 0.0


def _pass_rate_for_type(
    results: tuple[ExtractionEvalResult, ...],
    case_type: ExtractionCaseType,
) -> float:
    typed = tuple(result for result in results if result.case_type == case_type)
    return _rate(result.passed for result in typed)


def main() -> None:
    parser = ArgumentParser(description="Evaluate official-source RAG extraction.")
    parser.add_argument("--show-passing", action="store_true")
    args = parser.parse_args()
    print(render_report(evaluate_extraction(), show_passing=args.show_passing))


if __name__ == "__main__":
    main()
