"""End-to-end evaluation for uploaded-policy RAG."""

from __future__ import annotations

import json
import time
from argparse import ArgumentParser
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, cast

from app.integrations.openai import JsonCompleter
from app.modules.policy.parsing import parse_document
from app.modules.qa.contracts import ConsultationEvidence
from app.rag.embeddings import HashingEmbedder
from app.rag.policy.generation import generate_policy_answer
from app.rag.policy.retrieval import retrieve_policy_context
from evals.rag.policy.retrieval import (
    EVAL_FIXTURE as RETRIEVAL_FIXTURE,
)
from evals.rag.policy.retrieval import (
    PolicyEvalCase,
    _case_from_json,
    _case_with_session_tokens,
    _InMemoryPolicyStore,
    _records_from_documents,
    _resolve_sample_dir,
    _text_matches_expected_group,
)

EVAL_FIXTURE = Path(__file__).resolve().parent / "e2e_dataset.json"


@dataclass(frozen=True)
class PolicyRagE2ECase:
    id: str
    query: str
    session_ids: tuple[str, ...]
    expected_status: Literal["answered", "no_data"]
    expected_term_groups: tuple[tuple[str, ...], ...]
    must_include_groups: tuple[tuple[str, ...], ...]
    must_not_include: tuple[str, ...]


@dataclass(frozen=True)
class PolicyRagE2EResult:
    case_id: str
    query: str
    passed: bool
    retrieval_matched: bool
    status_matched: bool
    citation_valid: bool
    must_include_covered: bool
    must_not_include_clean: bool
    answer_status: Literal["answered", "no_data"]
    answer_generation: str
    evidence_ids: tuple[str, ...]
    hit_texts: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class PolicyRagE2EReport:
    passed: int
    total: int
    elapsed_seconds: float
    results: tuple[PolicyRagE2EResult, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def retrieval_match_rate(self) -> float:
        return _rate(result.retrieval_matched for result in self.results)

    @property
    def answer_contract_rate(self) -> float:
        return _rate(
            result.status_matched
            and result.citation_valid
            and result.must_include_covered
            and result.must_not_include_clean
            for result in self.results
        )


def load_e2e_eval_cases(path: Path = EVAL_FIXTURE) -> tuple[PolicyRagE2ECase, ...]:
    raw_retrieval = json.loads(RETRIEVAL_FIXTURE.read_text(encoding="utf-8"))
    retrieval_cases = {
        case.id: case for case in (_case_from_json(item) for item in raw_retrieval["cases"])
    }
    raw_cases = cast(list[dict[str, object]], json.loads(path.read_text(encoding="utf-8")))
    return tuple(_case_from_json_e2e(raw, retrieval_cases) for raw in raw_cases)


def evaluate_e2e(
    cases: tuple[PolicyRagE2ECase, ...] | None = None,
    *,
    complete: JsonCompleter | None = None,
) -> PolicyRagE2EReport:
    active_completer = complete or offline_extractive_completer
    active_cases = cases if cases is not None else load_e2e_eval_cases()
    raw_retrieval = json.loads(RETRIEVAL_FIXTURE.read_text(encoding="utf-8"))
    sample_dir = _resolve_sample_dir(None, source=str(raw_retrieval["source"]))
    embedder = HashingEmbedder()
    created_at = datetime.now(UTC)
    records = _records_from_documents(
        raw_retrieval["documents"],
        embedder,
        sample_dir,
        parse=parse_document,
        created_at=created_at,
    )
    store = _InMemoryPolicyStore(records)
    expires_at = created_at + timedelta(hours=1)
    started = time.perf_counter()
    results = tuple(
        _evaluate_case(
            _case_with_signed_sessions(case, expires_at=expires_at),
            store=store,
            embedder=embedder,
            complete=active_completer,
        )
        for case in active_cases
    )

    return PolicyRagE2EReport(
        passed=sum(result.passed for result in results),
        total=len(results),
        elapsed_seconds=time.perf_counter() - started,
        results=results,
    )


def offline_extractive_completer(_: str, user: str) -> dict[str, object]:
    """Select all retrieved evidence so E2E focuses on RAG wiring."""

    payload = json.loads(user)
    evidence = cast(list[dict[str, object]], payload.get("evidence", []))
    evidence_ids = [str(item.get("id", "")) for item in evidence if item.get("id")]
    return {
        "confirmed_fact": "선택한 근거에서 확인되는 내용입니다.",
        "guidance": None,
        "evidence_ids": evidence_ids,
        "suggestions": [],
        "limitations": [],
    }


def render_report(report: PolicyRagE2EReport, *, show_passing: bool = False) -> str:
    lines = [
        (
            f"passed={report.passed}/{report.total} "
            f"pass_rate={report.pass_rate:.3f} "
            f"retrieval_match={report.retrieval_match_rate:.3f} "
            f"answer_contract={report.answer_contract_rate:.3f} "
            f"elapsed_s={report.elapsed_seconds:.2f}"
        )
    ]

    for result in report.results:
        if result.passed and not show_passing:
            continue
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"{status} {result.case_id} "
            f"retrieval={result.retrieval_matched} "
            f"status={result.answer_status} generation={result.answer_generation}"
        )
        for note in result.notes:
            lines.append(f"  - {note}")
        if result.evidence_ids:
            lines.append(f"  evidence: {', '.join(result.evidence_ids)}")
        if result.hit_texts:
            lines.append(f"  top_hit: {result.hit_texts[0]}")

    return "\n".join(lines)


def _case_from_json_e2e(
    raw: dict[str, object],
    retrieval_cases: dict[str, PolicyEvalCase],
) -> PolicyRagE2ECase:
    base_case = _base_retrieval_case(raw, retrieval_cases)
    must_include_groups = raw.get("must_include_groups")
    return PolicyRagE2ECase(
        id=str(raw["id"]),
        query=base_case.query,
        session_ids=base_case.session_ids,
        expected_status=_expected_status(raw["expected_status"]),
        expected_term_groups=base_case.expected_term_groups,
        must_include_groups=(
            _string_groups(must_include_groups)
            if must_include_groups is not None
            else base_case.expected_term_groups
        ),
        must_not_include=_string_tuple(raw["must_not_include"]),
    )


def _base_retrieval_case(
    raw: dict[str, object],
    retrieval_cases: dict[str, PolicyEvalCase],
) -> PolicyEvalCase:
    retrieval_case_id = raw.get("retrieval_case_id")
    if retrieval_case_id is not None:
        return retrieval_cases[str(retrieval_case_id)]

    return PolicyEvalCase(
        id=str(raw["id"]),
        query=str(raw["query"]),
        session_ids=_string_tuple(raw["session_ids"]),
        expected_session_id="",
        expected_term_groups=_string_groups(raw["must_include_groups"]),
    )


def _evaluate_case(
    case: PolicyRagE2ECase,
    *,
    store: _InMemoryPolicyStore,
    embedder: HashingEmbedder,
    complete: JsonCompleter,
) -> PolicyRagE2EResult:
    hits = retrieve_policy_context(
        list(case.session_ids),
        case.query,
        top_k=5,
        store=store,
        embedder=embedder,
    )
    evidence = tuple(
        ConsultationEvidence(
            id=f"session:{index}",
            fact=f"업로드 증권 원문 발췌: {hit.chunk.text}",
        )
        for index, hit in enumerate(hits, start=1)
    )
    answer = generate_policy_answer(case.query, evidence, complete=complete)
    answer_status: Literal["answered", "no_data"] = (
        "no_data" if answer.generation == "fallback" else "answered"
    )
    visible_text = _normalize(" ".join((answer.answer, *answer.suggestions, *answer.limitations)))
    retrieval_matched = case.expected_status == "no_data" or any(
        _text_matches_expected_group(hit.chunk.text, case.expected_term_groups) for hit in hits
    )
    evidence_ids = {item.id for item in evidence}
    citation_valid = all(item_id in evidence_ids for item_id in answer.evidence_ids)
    status_matched = answer_status == case.expected_status
    must_include_covered = all(
        any(_normalize(term) in visible_text for term in group)
        for group in case.must_include_groups
    )
    must_not_include_clean = all(
        _normalize(term) not in visible_text for term in case.must_not_include
    )
    passed = (
        retrieval_matched
        and status_matched
        and citation_valid
        and must_include_covered
        and must_not_include_clean
    )

    return PolicyRagE2EResult(
        case_id=case.id,
        query=case.query,
        passed=passed,
        retrieval_matched=retrieval_matched,
        status_matched=status_matched,
        citation_valid=citation_valid,
        must_include_covered=must_include_covered,
        must_not_include_clean=must_not_include_clean,
        answer_status=answer_status,
        answer_generation=answer.generation,
        evidence_ids=answer.evidence_ids,
        hit_texts=tuple(hit.chunk.text[:160].replace("\n", " ") for hit in hits),
        notes=_notes(
            retrieval_matched=retrieval_matched,
            status_matched=status_matched,
            citation_valid=citation_valid,
            must_include_covered=must_include_covered,
            must_not_include_clean=must_not_include_clean,
            expected_status=case.expected_status,
            answer_status=answer_status,
        ),
    )


def _case_with_signed_sessions(
    case: PolicyRagE2ECase,
    *,
    expires_at: datetime,
) -> PolicyRagE2ECase:
    retrieval_case = PolicyEvalCase(
        id=case.id,
        query=case.query,
        session_ids=case.session_ids,
        expected_session_id="",
        expected_term_groups=case.expected_term_groups,
    )
    signed = _case_with_session_tokens(retrieval_case, expires_at=expires_at)
    return PolicyRagE2ECase(
        id=case.id,
        query=case.query,
        session_ids=signed.session_ids,
        expected_status=case.expected_status,
        expected_term_groups=case.expected_term_groups,
        must_include_groups=case.must_include_groups,
        must_not_include=case.must_not_include,
    )


def _notes(
    *,
    retrieval_matched: bool,
    status_matched: bool,
    citation_valid: bool,
    must_include_covered: bool,
    must_not_include_clean: bool,
    expected_status: str,
    answer_status: str,
) -> tuple[str, ...]:
    notes: list[str] = []
    if not retrieval_matched:
        notes.append("expected evidence was not retrieved")
    if not status_matched:
        notes.append(f"expected status {expected_status}, got {answer_status}")
    if not citation_valid:
        notes.append("answer cited evidence that was not retrieved")
    if not must_include_covered:
        notes.append("answer did not include required terms")
    if not must_not_include_clean:
        notes.append("answer included forbidden terms")
    return tuple(notes)


def _expected_status(value: object) -> Literal["answered", "no_data"]:
    status = str(value)
    if status not in {"answered", "no_data"}:
        raise ValueError(f"unknown expected_status: {status}")
    return cast(Literal["answered", "no_data"], status)


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(list[object], value))


def _string_groups(value: object) -> tuple[tuple[str, ...], ...]:
    return tuple(_string_tuple(group) for group in cast(list[object], value))


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _rate(values: Iterable[bool]) -> float:
    items = tuple(bool(value) for value in values)
    return sum(1 for item in items if item) / len(items) if items else 0.0


def _parse_args() -> tuple[Path, bool]:
    parser = ArgumentParser(description="Evaluate uploaded-policy RAG E2E.")
    parser.add_argument("--path", type=Path, default=EVAL_FIXTURE)
    parser.add_argument("--show-passing", action="store_true")
    args = parser.parse_args()
    return cast(Path, args.path), bool(args.show_passing)


if __name__ == "__main__":
    path, show_passing = _parse_args()
    print(render_report(evaluate_e2e(load_e2e_eval_cases(path)), show_passing=show_passing))
