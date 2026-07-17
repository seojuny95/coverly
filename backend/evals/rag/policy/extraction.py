"""Extraction evaluation for uploaded-policy RAG indexing inputs.

The fixture intentionally stores symbolic PII markers only. Synthetic values are
generated in memory during evaluation and are never rendered in reports.
"""

from __future__ import annotations

import json
import unicodedata
from argparse import ArgumentParser
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from app.modules.policy.models import ParsedDocument, Table
from app.rag.embeddings import HashingEmbedder
from app.rag.policy.indexing import build_policy_vector_records
from app.rag.policy.models import PolicyContentType

EVAL_FIXTURE = Path(__file__).resolve().parent / "extraction_dataset.json"

PiiKind = Literal[
    "mobile_phone",
    "landline_phone",
    "landline_phone_no_hyphen",
    "representative_phone",
    "representative_phone_no_hyphen",
    "email",
    "rrn",
]
ExtractionCheckName = Literal[
    "records",
    "content_types",
    "table_indexes",
    "must_include",
    "pii_masked",
    "mask_tokens",
]


@dataclass(frozen=True)
class PolicyExtractionEvalCase:
    id: str
    text_lines: tuple[str, ...]
    tables: tuple[Table, ...]
    generated_pii: tuple[PiiKind, ...]
    expected_content_types: tuple[PolicyContentType, ...]
    expected_table_indexes: tuple[int, ...]
    must_include_groups: tuple[tuple[str, ...], ...]
    expected_mask_tokens: tuple[str, ...]


@dataclass(frozen=True)
class PolicyExtractionEvalResult:
    case_id: str
    passed: bool
    record_count: int
    content_types: tuple[PolicyContentType, ...]
    table_indexes: tuple[int, ...]
    records_present: bool
    content_types_matched: bool
    table_indexes_matched: bool
    must_include_covered: bool
    pii_masked: bool
    mask_tokens_present: bool
    failed_checks: tuple[ExtractionCheckName, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class PolicyExtractionEvalReport:
    passed: int
    total: int
    results: tuple[PolicyExtractionEvalResult, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def content_type_match_rate(self) -> float:
        return _rate(result.content_types_matched for result in self.results)

    @property
    def table_index_match_rate(self) -> float:
        return _rate(result.table_indexes_matched for result in self.results)

    @property
    def must_include_coverage(self) -> float:
        return _rate(result.must_include_covered for result in self.results)

    @property
    def pii_mask_rate(self) -> float:
        return _rate(result.pii_masked for result in self.results)

    @property
    def mask_token_rate(self) -> float:
        return _rate(result.mask_tokens_present for result in self.results)


def load_extraction_eval_cases(
    path: Path = EVAL_FIXTURE,
) -> tuple[PolicyExtractionEvalCase, ...]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    return tuple(_case_from_json(raw) for raw in cast(list[dict[str, object]], raw_cases))


def evaluate_policy_extraction(
    cases: tuple[PolicyExtractionEvalCase, ...] | None = None,
) -> PolicyExtractionEvalReport:
    active_cases = cases if cases is not None else load_extraction_eval_cases()
    results = tuple(_evaluate_case(case) for case in active_cases)
    return PolicyExtractionEvalReport(
        passed=sum(1 for result in results if result.passed),
        total=len(results),
        results=results,
    )


def render_report(
    report: PolicyExtractionEvalReport,
    *,
    show_passing: bool = False,
) -> str:
    lines = [
        (
            f"passed={report.passed}/{report.total} "
            f"pass_rate={report.pass_rate:.3f} "
            f"content_types={report.content_type_match_rate:.3f} "
            f"table_indexes={report.table_index_match_rate:.3f} "
            f"must_include={report.must_include_coverage:.3f} "
            f"pii_masked={report.pii_mask_rate:.3f} "
            f"mask_tokens={report.mask_token_rate:.3f}"
        )
    ]
    for result in report.results:
        if result.passed and not show_passing:
            continue
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"{status} {result.case_id} "
            f"records={result.record_count} "
            f"content_types={','.join(result.content_types) or '-'} "
            f"table_indexes={','.join(str(index) for index in result.table_indexes) or '-'}"
        )
        for note in result.notes:
            lines.append(f"  - {note}")
    return "\n".join(lines)


def _evaluate_case(case: PolicyExtractionEvalCase) -> PolicyExtractionEvalResult:
    generated = _generated_pii_values(case.generated_pii)
    document = _document_from_case(case, generated)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    records = build_policy_vector_records(
        document,
        session_id=f"eval-{case.id}",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        embedder=HashingEmbedder(),
    )

    record_text = "\n".join(record.chunk.text for record in records)
    content_types = tuple(record.chunk.content_type for record in records)
    table_indexes = tuple(
        record.chunk.table_index for record in records if record.chunk.table_index is not None
    )
    expected_record_count = len(case.expected_content_types)
    records_present = len(records) >= expected_record_count
    content_types_matched = _contains_all(content_types, case.expected_content_types)
    table_indexes_matched = tuple(sorted(table_indexes)) == tuple(
        sorted(case.expected_table_indexes)
    )
    must_include_covered = _text_matches_expected_groups(record_text, case.must_include_groups)
    unmasked_kinds = tuple(
        kind for kind, value in generated.items() if value and value in record_text
    )
    pii_masked = not unmasked_kinds
    missing_mask_tokens = tuple(
        token for token in case.expected_mask_tokens if token not in record_text
    )
    mask_tokens_present = not missing_mask_tokens

    failed_checks: list[ExtractionCheckName] = []
    notes: list[str] = []
    if not records_present:
        failed_checks.append("records")
        notes.append(f"expected at least {expected_record_count} indexed records")
    if not content_types_matched:
        failed_checks.append("content_types")
        notes.append(
            "missing expected content types: "
            + ", ".join(_missing_items(content_types, case.expected_content_types))
        )
    if not table_indexes_matched:
        failed_checks.append("table_indexes")
        notes.append(f"expected table indexes {case.expected_table_indexes}, got {table_indexes}")
    if not must_include_covered:
        failed_checks.append("must_include")
        notes.append("one or more required term groups were not preserved")
    if not pii_masked:
        failed_checks.append("pii_masked")
        notes.append(
            "unmasked generated pii kinds: " + ", ".join(str(kind) for kind in unmasked_kinds)
        )
    if not mask_tokens_present:
        failed_checks.append("mask_tokens")
        notes.append("missing mask tokens: " + ", ".join(missing_mask_tokens))

    return PolicyExtractionEvalResult(
        case_id=case.id,
        passed=not failed_checks,
        record_count=len(records),
        content_types=content_types,
        table_indexes=table_indexes,
        records_present=records_present,
        content_types_matched=content_types_matched,
        table_indexes_matched=table_indexes_matched,
        must_include_covered=must_include_covered,
        pii_masked=pii_masked,
        mask_tokens_present=mask_tokens_present,
        failed_checks=tuple(failed_checks),
        notes=tuple(notes),
    )


def _document_from_case(
    case: PolicyExtractionEvalCase,
    generated: dict[PiiKind, str],
) -> ParsedDocument:
    text = "\n".join(_replace_generated_pii(line, generated) for line in case.text_lines)
    tables: list[Table] = []
    for table in case.tables:
        tables.append(
            tuple(
                tuple(
                    None if cell is None else _replace_generated_pii(cell, generated)
                    for cell in row
                )
                for row in table
            )
        )
    return ParsedDocument(text=text, layout_text="", tables=tuple(tables))


def _replace_generated_pii(text: str, generated: dict[PiiKind, str]) -> str:
    result = text
    for kind, value in generated.items():
        result = result.replace("{" + kind + "}", value)
    return result


def _generated_pii_values(kinds: tuple[PiiKind, ...]) -> dict[PiiKind, str]:
    values = {
        "mobile_phone": "010-" + "1234" + "-" + "5678",
        "landline_phone": "02-" + "2345" + "-" + "6789",
        "landline_phone_no_hyphen": "02" + "2345" + "6789",
        "representative_phone": "1688-" + "1234",
        "representative_phone_no_hyphen": "1688" + "1234",
        "email": "person" + "@example.invalid",
        "rrn": "900101-" + "1234567",
    }
    return {kind: values[kind] for kind in kinds}


def _case_from_json(raw: dict[str, object]) -> PolicyExtractionEvalCase:
    return PolicyExtractionEvalCase(
        id=str(raw["id"]),
        text_lines=_string_tuple(raw["text_lines"]),
        tables=_tables_from_json(raw["tables"]),
        generated_pii=_pii_tuple(raw["generated_pii"]),
        expected_content_types=_content_type_tuple(raw["expected_content_types"]),
        expected_table_indexes=tuple(
            int(str(item)) for item in cast(list[object], raw["expected_table_indexes"])
        ),
        must_include_groups=_string_groups(raw["must_include_groups"]),
        expected_mask_tokens=_string_tuple(raw["expected_mask_tokens"]),
    )


def _tables_from_json(value: object) -> tuple[Table, ...]:
    tables: list[Table] = []
    for raw_table in cast(list[object], value):
        rows: list[tuple[str | None, ...]] = []
        for raw_row in cast(list[object], raw_table):
            rows.append(
                tuple(
                    None if cell is None else str(cell)
                    for cell in cast(list[object | None], raw_row)
                )
            )
        tables.append(tuple(rows))
    return tuple(tables)


def _content_type_tuple(value: object) -> tuple[PolicyContentType, ...]:
    allowed = {"text", "table"}
    content_types = tuple(str(item) for item in cast(list[object], value))
    unknown = tuple(item for item in content_types if item not in allowed)
    if unknown:
        raise ValueError(f"unknown content types: {unknown}")
    return cast(tuple[PolicyContentType, ...], content_types)


def _pii_tuple(value: object) -> tuple[PiiKind, ...]:
    allowed = {
        "mobile_phone",
        "landline_phone",
        "landline_phone_no_hyphen",
        "representative_phone",
        "representative_phone_no_hyphen",
        "email",
        "rrn",
    }
    kinds = tuple(str(item) for item in cast(list[object], value))
    unknown = tuple(item for item in kinds if item not in allowed)
    if unknown:
        raise ValueError(f"unknown generated pii kinds: {unknown}")
    return cast(tuple[PiiKind, ...], kinds)


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(list[object], value))


def _string_groups(value: object) -> tuple[tuple[str, ...], ...]:
    return tuple(_string_tuple(group) for group in cast(list[object], value))


def _contains_all(actual: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    actual_counts = {item: actual.count(item) for item in set(actual)}
    return all(actual_counts.get(item, 0) >= expected.count(item) for item in set(expected))


def _missing_items(actual: tuple[str, ...], expected: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item for item in expected if actual.count(item) < expected.count(item))


def _text_matches_expected_groups(
    text: str,
    expected_term_groups: tuple[tuple[str, ...], ...],
) -> bool:
    return all(
        all(_normalize_match_text(term) in _normalize_match_text(text) for term in group)
        for group in expected_term_groups
    )


def _normalize_match_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(char for char in normalized if char.isalnum() or ("가" <= char <= "힣"))


def _rate(values: Iterable[object]) -> float:
    items = tuple(bool(value) for value in values)
    return sum(1 for value in items if value) / len(items) if items else 0.0


def _parse_args() -> bool:
    parser = ArgumentParser(description="Evaluate uploaded-policy RAG extraction.")
    parser.add_argument("--show-passing", action="store_true")
    args = parser.parse_args()
    return bool(args.show_passing)


if __name__ == "__main__":
    print(render_report(evaluate_policy_extraction(), show_passing=_parse_args()))
