"""Fixed-context evaluation for uploaded-policy RAG generation.

This evaluates the generation step after retrieval has already supplied
session-scoped evidence. It intentionally does not run policy retrieval, so
retrieval ranking quality and answer-generation quality stay separable.
"""

from __future__ import annotations

import json
import re
from argparse import ArgumentParser
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from app.core.config import get_settings
from app.integrations.openai import JsonCompleter
from app.modules.qa.contracts import ConsultationEvidence, InsuredDemographics
from app.rag.policy.generation import PolicyGenerationResult, generate_policy_answer
from evals.rag.data import string_groups as _string_groups
from evals.rag.data import string_tuple as _string_tuple
from evals.rag.text import missing_term_groups as _missing_term_groups
from evals.rag.text import normalize_whitespace as _normalize
from evals.rag.text import present_terms as _present_terms

PRACTICE_FIXTURE = Path(__file__).resolve().parent / "generation_dataset.json"
TEST_FIXTURE = Path(__file__).resolve().parent / "generation_test_dataset.json"
# Backward-compatible alias for callers that imported the original fixture name.
EVAL_FIXTURE = PRACTICE_FIXTURE

GenerationCheckName = Literal[
    "status",
    "generation",
    "citation_validity",
    "allowed_evidence",
    "required_evidence",
    "forbidden_evidence",
    "must_include",
    "must_not_include",
]


@dataclass(frozen=True)
class PolicyGenerationEvalCase:
    id: str
    category: str
    risk_tags: tuple[str, ...]
    question: str
    demographics: InsuredDemographics
    evidence: tuple[ConsultationEvidence, ...]
    expected_status: Literal["answered", "refused", "no_data"]
    expected_generation: Literal["llm", "fallback"]
    allowed_evidence_ids: tuple[str, ...]
    required_evidence_ids: tuple[str, ...]
    forbidden_evidence_ids: tuple[str, ...]
    must_include_groups: tuple[tuple[str, ...], ...]
    must_not_include: tuple[str, ...]


@dataclass(frozen=True)
class PolicyGenerationEvalResult:
    case_id: str
    question: str
    passed: bool
    status_matched: bool
    generation_matched: bool
    citation_valid: bool
    allowed_evidence_clean: bool
    required_evidence_covered: bool
    forbidden_evidence_clean: bool
    must_include_covered: bool
    must_not_include_clean: bool
    failed_checks: tuple[GenerationCheckName, ...]
    notes: tuple[str, ...]
    answer_status: str
    answer_generation: str
    answer: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class PolicyGenerationEvalReport:
    passed: int
    total: int
    results: tuple[PolicyGenerationEvalResult, ...]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def status_match_rate(self) -> float:
        return _rate(result.status_matched for result in self.results)

    @property
    def generation_match_rate(self) -> float:
        return _rate(result.generation_matched for result in self.results)

    @property
    def citation_valid_rate(self) -> float:
        return _rate(result.citation_valid for result in self.results)

    @property
    def allowed_evidence_clean_rate(self) -> float:
        return _rate(result.allowed_evidence_clean for result in self.results)

    @property
    def required_evidence_coverage(self) -> float:
        return _rate(result.required_evidence_covered for result in self.results)

    @property
    def forbidden_evidence_clean_rate(self) -> float:
        return _rate(result.forbidden_evidence_clean for result in self.results)

    @property
    def must_include_coverage(self) -> float:
        return _rate(result.must_include_covered for result in self.results)

    @property
    def must_not_include_clean_rate(self) -> float:
        return _rate(result.must_not_include_clean for result in self.results)


def load_generation_eval_cases(
    path: Path = EVAL_FIXTURE,
) -> tuple[PolicyGenerationEvalCase, ...]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    return tuple(_case_from_json(raw) for raw in raw_cases)


def load_practice_eval_cases() -> tuple[PolicyGenerationEvalCase, ...]:
    """Load the policy generation practice cases."""

    return load_generation_eval_cases(PRACTICE_FIXTURE)


def evaluate_generation(
    cases: tuple[PolicyGenerationEvalCase, ...] | None = None,
    *,
    complete: JsonCompleter | None = None,
) -> PolicyGenerationEvalReport:
    if complete is None and not get_settings().openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live policy generation evaluation")

    active_cases = cases if cases is not None else load_practice_eval_cases()
    results = tuple(
        _evaluate_case(case, _answer_case(case, complete=complete)) for case in active_cases
    )

    return PolicyGenerationEvalReport(
        passed=sum(1 for result in results if result.passed),
        total=len(results),
        results=results,
    )


def offline_lexical_completer(_: str, user: str) -> dict[str, object]:
    """Select evidence with deterministic lexical overlap for offline checks."""

    payload = json.loads(user)
    question_terms = set(_lexical_terms(str(payload.get("question", ""))))
    evidence_items = cast(list[dict[str, object]], payload.get("evidence", []))
    scored: list[tuple[int, str]] = []
    for item in evidence_items:
        evidence_id = str(item.get("id", ""))
        fact_terms = set(_lexical_terms(str(item.get("fact", ""))))
        scored.append((len(question_terms & fact_terms), evidence_id))

    max_score = max((score for score, _evidence_id in scored), default=0)
    evidence_ids = [
        evidence_id for score, evidence_id in scored if score == max_score and score > 0
    ][:4]
    return {
        "confirmed_fact": "선택한 근거에서 확인되는 내용입니다.",
        "guidance": None,
        "evidence_ids": evidence_ids,
        "suggestions": [],
        "limitations": [],
    }


def render_report(report: PolicyGenerationEvalReport, *, show_passing: bool = False) -> str:
    lines = [
        (
            f"passed={report.passed}/{report.total} "
            f"pass_rate={report.pass_rate:.3f} "
            f"status={report.status_match_rate:.3f} "
            f"generation={report.generation_match_rate:.3f} "
            f"citations={report.citation_valid_rate:.3f} "
            f"allowed_evidence={report.allowed_evidence_clean_rate:.3f} "
            f"required_evidence={report.required_evidence_coverage:.3f} "
            f"forbidden_evidence={report.forbidden_evidence_clean_rate:.3f} "
            f"must_include={report.must_include_coverage:.3f} "
            f"must_not_include={report.must_not_include_clean_rate:.3f}"
        )
    ]

    for result in report.results:
        if result.passed and not show_passing:
            continue
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"{status} {result.case_id} "
            f"status={result.answer_status} generation={result.answer_generation}"
        )
        for note in result.notes:
            lines.append(f"  - {note}")
        if result.answer:
            lines.append(f"  answer: {result.answer}")
        if result.citation_ids:
            lines.append(f"  citations: {', '.join(result.citation_ids)}")

    return "\n".join(lines)


def _case_from_json(raw: dict[str, object]) -> PolicyGenerationEvalCase:
    expected_status = str(raw["expected_status"])
    if expected_status not in {"answered", "refused", "no_data"}:
        raise ValueError(f"unknown expected_status: {expected_status}")
    expected_generation = str(raw["expected_generation"])
    if expected_generation not in {"llm", "fallback"}:
        raise ValueError(f"unknown expected_generation: {expected_generation}")

    return PolicyGenerationEvalCase(
        id=str(raw["id"]),
        category=str(raw["category"]),
        risk_tags=_string_tuple(raw["risk_tags"]),
        question=str(raw["question"]),
        demographics=InsuredDemographics.model_validate(raw["demographics"]),
        evidence=tuple(
            ConsultationEvidence.model_validate(item)
            for item in cast(list[object], raw["evidence"])
        ),
        expected_status=cast(Literal["answered", "refused", "no_data"], expected_status),
        expected_generation=cast(Literal["llm", "fallback"], expected_generation),
        allowed_evidence_ids=_string_tuple(raw["allowed_evidence_ids"]),
        required_evidence_ids=_string_tuple(raw["required_evidence_ids"]),
        forbidden_evidence_ids=_string_tuple(raw["forbidden_evidence_ids"]),
        must_include_groups=_string_groups(raw["must_include_groups"]),
        must_not_include=_string_tuple(raw["must_not_include"]),
    )


def _answer_case(
    case: PolicyGenerationEvalCase,
    *,
    complete: JsonCompleter | None,
) -> PolicyGenerationResult:
    return generate_policy_answer(
        case.question,
        case.evidence,
        complete=complete,
    )


def _evaluate_case(
    case: PolicyGenerationEvalCase,
    answer: PolicyGenerationResult,
) -> PolicyGenerationEvalResult:
    evidence_ids = {item.id for item in case.evidence}
    citation_ids = answer.evidence_ids
    answer_text = _normalize(answer.answer)
    visible_text = _normalize(" ".join((answer.answer, *answer.suggestions, *answer.limitations)))

    answer_status = _answer_status(answer)
    status_matched = answer_status == case.expected_status
    generation_matched = answer.generation == case.expected_generation
    citation_valid = all(citation_id in evidence_ids for citation_id in citation_ids)
    allowed_evidence_clean = all(
        citation_id in case.allowed_evidence_ids for citation_id in citation_ids
    )
    required_evidence_covered = all(
        evidence_id in citation_ids for evidence_id in case.required_evidence_ids
    )
    forbidden_evidence_clean = all(
        evidence_id not in citation_ids for evidence_id in case.forbidden_evidence_ids
    )
    must_include_covered = all(
        any(_normalize(term) in answer_text for term in group) for group in case.must_include_groups
    )
    must_not_include_clean = all(
        _normalize(term) not in visible_text for term in case.must_not_include
    )

    checks: tuple[tuple[GenerationCheckName, bool], ...] = (
        ("status", status_matched),
        ("generation", generation_matched),
        ("citation_validity", citation_valid),
        ("allowed_evidence", allowed_evidence_clean),
        ("required_evidence", required_evidence_covered),
        ("forbidden_evidence", forbidden_evidence_clean),
        ("must_include", must_include_covered),
        ("must_not_include", must_not_include_clean),
    )
    failed_checks = tuple(name for name, passed in checks if not passed)

    return PolicyGenerationEvalResult(
        case_id=case.id,
        question=case.question,
        passed=not failed_checks,
        status_matched=status_matched,
        generation_matched=generation_matched,
        citation_valid=citation_valid,
        allowed_evidence_clean=allowed_evidence_clean,
        required_evidence_covered=required_evidence_covered,
        forbidden_evidence_clean=forbidden_evidence_clean,
        must_include_covered=must_include_covered,
        must_not_include_clean=must_not_include_clean,
        failed_checks=failed_checks,
        notes=_notes(case, answer, failed_checks, citation_ids, visible_text),
        answer_status=answer_status,
        answer_generation=answer.generation,
        answer=answer.answer,
        citation_ids=citation_ids,
    )


def _notes(
    case: PolicyGenerationEvalCase,
    answer: PolicyGenerationResult,
    failed_checks: tuple[GenerationCheckName, ...],
    citation_ids: tuple[str, ...],
    visible_text: str,
) -> tuple[str, ...]:
    notes: list[str] = []
    if "status" in failed_checks:
        notes.append(f"expected status {case.expected_status}, got {_answer_status(answer)}")
    if "generation" in failed_checks:
        notes.append(f"expected generation {case.expected_generation}, got {answer.generation}")
    if "citation_validity" in failed_checks:
        invalid = sorted(set(citation_ids) - {item.id for item in case.evidence})
        notes.append(f"invalid evidence ids: {', '.join(invalid)}")
    if "allowed_evidence" in failed_checks:
        disallowed = sorted(set(citation_ids) - set(case.allowed_evidence_ids))
        notes.append(f"disallowed evidence ids cited: {', '.join(disallowed)}")
    if "required_evidence" in failed_checks:
        missing = sorted(set(case.required_evidence_ids) - set(citation_ids))
        notes.append(f"missing required evidence ids: {', '.join(missing)}")
    if "forbidden_evidence" in failed_checks:
        forbidden = sorted(set(case.forbidden_evidence_ids) & set(citation_ids))
        notes.append(f"forbidden evidence ids cited: {', '.join(forbidden)}")
    if "must_include" in failed_checks:
        missing_groups = _missing_term_groups(case.must_include_groups, answer.answer)
        notes.append(f"missing required answer groups: {', '.join(missing_groups)}")
    if "must_not_include" in failed_checks:
        present = _present_terms(case.must_not_include, visible_text)
        notes.append(f"forbidden answer terms present: {', '.join(present)}")
    return tuple(notes)


def _answer_status(answer: PolicyGenerationResult) -> Literal["answered", "no_data"]:
    if answer.generation == "fallback":
        return "no_data"
    return "answered"


_LEXICAL_STOPWORDS = {
    "보험",
    "보험증권",
    "증권",
    "원문",
    "발췌",
    "확인",
    "확인되는",
    "내용",
    "알려줘",
    "뭐야",
    "무엇",
    "어떻게",
    "경우",
    "현재",
    "가입",
    "질문",
}


def _lexical_terms(text: str) -> tuple[str, ...]:
    return tuple(
        term
        for term in re.findall(r"[가-힣A-Za-z0-9]+", text)
        if len(term) >= 2 and term not in _LEXICAL_STOPWORDS
    )


def _rate(values: Iterable[bool]) -> float:
    items = tuple(bool(value) for value in values)
    return sum(1 for item in items if item) / len(items) if items else 0.0


def _parse_args() -> tuple[Path | None, Literal["practice", "test"], bool, bool]:
    parser = ArgumentParser(description="Evaluate uploaded-policy RAG generation.")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--set", choices=("practice", "test"), default="practice")
    parser.add_argument(
        "--offline-lexical",
        action="store_true",
        help="Run a deterministic lexical completer instead of the live LLM completer.",
    )
    parser.add_argument("--show-passing", action="store_true")
    args = parser.parse_args()
    return (
        cast(Path | None, args.path),
        cast(Literal["practice", "test"], args.set),
        bool(args.offline_lexical),
        bool(args.show_passing),
    )


if __name__ == "__main__":
    path, dataset, use_offline_lexical, show_passing = _parse_args()
    if path is not None:
        cases = load_generation_eval_cases(path)
    elif dataset == "test":
        cases = load_generation_eval_cases(TEST_FIXTURE)
    else:
        cases = load_practice_eval_cases()
    report = evaluate_generation(
        cases,
        complete=offline_lexical_completer if use_offline_lexical else None,
    )
    print(render_report(report, show_passing=show_passing))
