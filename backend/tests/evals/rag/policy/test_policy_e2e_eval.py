import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from evals.rag.policy.e2e import (
    EVAL_FIXTURE,
    PolicyRagE2ECase,
    evaluate_e2e,
    load_e2e_eval_cases,
    offline_extractive_completer,
    render_report,
)


@contextmanager
def _stub_retrieval_context(**_kwargs: object) -> Iterator[SimpleNamespace]:
    yield SimpleNamespace(
        store=SimpleNamespace(),
        embedder=SimpleNamespace(),
        expires_at=datetime.now(UTC),
        corpus_version="corpus-test",
        index_version="in-memory:corpus-test",
        map_session_ids=lambda session_ids: session_ids,
    )


def test_policy_rag_e2e_dataset_is_pii_safe_and_well_labeled() -> None:
    serialized = EVAL_FIXTURE.read_text(encoding="utf-8")
    raw = json.loads(serialized)
    cases = load_e2e_eval_cases()

    assert set(raw) == {"retrieval_cases", "extra_cases"}
    assert raw["retrieval_cases"]["include"] == "all"
    assert len(raw["extra_cases"]) >= 45
    assert len(cases) >= 170
    assert {case.expected_status for case in cases} == {"answered", "no_data"}
    assert all(case.must_include_groups for case in cases)
    assert "sample-" in serialized
    assert re.search(r"\b\d{6}-[1-4]\d{6}\b", serialized) is None
    assert re.search(r"\b01[016789]-?\d{3,4}-?\d{4}\b", serialized) is None
    assert re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", serialized) is None
    assert "계좌번호" not in serialized


def test_policy_rag_e2e_scores_retrieval_then_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = PolicyRagE2ECase(
        id="case",
        query="암진단비 얼마야?",
        session_ids=("session",),
        expected_status="answered",
        expected_term_groups=(("암진단비", "2,000만원"),),
        must_include_groups=(("암진단비",), ("2,000만원",)),
        must_not_include=("가입하세요",),
    )
    hit = SimpleNamespace(chunk=SimpleNamespace(text="암진단비(유사암제외) 가입금액 2,000만원"))

    monkeypatch.setattr(
        "evals.rag.policy.e2e.policy_retrieval_eval_context",
        _stub_retrieval_context,
    )
    monkeypatch.setattr("evals.rag.policy.e2e.retrieve_policy_context", lambda *_args, **_kw: [hit])

    report = evaluate_e2e((case,), complete=offline_extractive_completer)

    assert report.passed == 1
    assert report.pass_rate == 1.0
    assert report.retrieval_match_rate == 1.0
    assert report.metadata.retrieval_mode == "offline"
    assert report.metadata.generation_mode == "deterministic"
    assert report.metadata.corpus_version == "corpus-test"
    assert report.metadata.total_average_latency_seconds >= 0
    assert "passed=1/1" in render_report(report)


def test_policy_rag_e2e_reports_contract_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = PolicyRagE2ECase(
        id="case",
        query="암진단비 얼마야?",
        session_ids=("session",),
        expected_status="answered",
        expected_term_groups=(("암진단비", "2,000만원"),),
        must_include_groups=(("암진단비",), ("2,000만원",)),
        must_not_include=("가입하세요",),
    )
    hit = SimpleNamespace(chunk=SimpleNamespace(text="질병수술비 가입금액 30만원"))

    monkeypatch.setattr(
        "evals.rag.policy.e2e.policy_retrieval_eval_context",
        _stub_retrieval_context,
    )
    monkeypatch.setattr("evals.rag.policy.e2e.retrieve_policy_context", lambda *_args, **_kw: [hit])

    report = evaluate_e2e((case,), complete=offline_extractive_completer)

    assert report.passed == 0
    assert report.results[0].notes == (
        "expected evidence was not retrieved",
        "answer did not include required terms",
    )
    assert "질병수술비 가입금액 30만원" not in render_report(report)


def test_policy_rag_e2e_rejects_unknown_execution_mode() -> None:
    with pytest.raises(ValueError, match="unknown generation mode"):
        evaluate_e2e((), generation_mode="typo")  # type: ignore[arg-type]
