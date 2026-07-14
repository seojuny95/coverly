import json
import re

import pytest

from app.schemas.consultation import ConsultationEvidence, InsuredDemographics
from app.services.rag.policy.evaluation.generation import (
    EVAL_FIXTURE,
    TEST_FIXTURE,
    PolicyGenerationEvalCase,
    evaluate_generation,
    load_generation_eval_cases,
    load_practice_eval_cases,
    render_report,
)


def test_policy_generation_eval_dataset_has_stable_schema() -> None:
    raw_cases = json.loads(EVAL_FIXTURE.read_text(encoding="utf-8"))
    expected_keys = {
        "id",
        "category",
        "risk_tags",
        "question",
        "demographics",
        "evidence",
        "expected_status",
        "expected_generation",
        "allowed_evidence_ids",
        "required_evidence_ids",
        "forbidden_evidence_ids",
        "must_include_groups",
        "must_not_include",
    }

    assert len(raw_cases) >= 6
    assert all(set(raw_case) == expected_keys for raw_case in raw_cases)


def test_policy_generation_eval_fixture_is_well_labeled() -> None:
    cases = load_practice_eval_cases()
    case_ids = [case.id for case in cases]

    assert len(cases) >= 80
    assert len(case_ids) == len(set(case_ids))
    assert len({case.category for case in cases}) >= 12
    assert sum(1 for case in cases if len(case.evidence) >= 3) >= 20
    assert sum(1 for case in cases if case.expected_generation == "fallback") >= 10
    assert {case.expected_generation for case in cases} == {"llm", "fallback"}
    assert {case.expected_status for case in cases} == {"answered", "no_data"}
    assert all(
        (case.expected_generation == "fallback") == (case.expected_status == "no_data")
        for case in cases
    )
    assert any(case.forbidden_evidence_ids for case in cases)
    assert all(
        evidence_id in {item.id for item in case.evidence}
        for case in cases
        for evidence_id in case.allowed_evidence_ids
    )
    assert all(
        evidence_id in case.allowed_evidence_ids
        for case in cases
        for evidence_id in case.required_evidence_ids
    )
    assert all(
        evidence_id not in case.allowed_evidence_ids
        for case in cases
        for evidence_id in case.forbidden_evidence_ids
    )
    assert all(case.must_not_include for case in cases)


def test_policy_generation_eval_dataset_does_not_contain_sample_pii() -> None:
    rendered = "\n".join(
        fixture.read_text(encoding="utf-8") for fixture in (EVAL_FIXTURE, TEST_FIXTURE)
    )
    assert "[이름]" in rendered
    assert "[전화번호]" in rendered
    assert "[계좌번호]" in rendered
    assert re.search(r"0\d{1,2}-?\d{3,4}-?\d{4}", rendered) is None
    assert re.search(r"\d{6}-?[1-4]\d{6}", rendered) is None
    assert re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", rendered) is None
    assert re.search(r"\d{2,6}-\d{2,6}-\d{2,8}", rendered) is None


def test_policy_generation_test_fixture_is_isolated_and_challenging() -> None:
    practice_cases = load_practice_eval_cases()
    test_cases = load_generation_eval_cases(TEST_FIXTURE)

    assert len(test_cases) >= 20
    assert {case.id for case in practice_cases}.isdisjoint(case.id for case in test_cases)
    assert all(len(case.evidence) >= 3 for case in test_cases)
    assert sum(case.expected_generation == "fallback" for case in test_cases) >= 5
    assert sum(len(case.required_evidence_ids) >= 2 for case in test_cases) >= 5


def test_policy_generation_eval_scores_contract_checks_with_stub_completer() -> None:
    demographics = InsuredDemographics(
        age=35,
        gender="여성",
        source="policy",
        status="verified_policy",
    )
    cases = (
        PolicyGenerationEvalCase(
            id="passing",
            category="basic_contract",
            risk_tags=("extractive_fact",),
            question="보험기간은?",
            demographics=demographics,
            evidence=(
                ConsultationEvidence(
                    id="session:1",
                    fact="업로드 증권 원문 발췌: 보험기간 2024년 ~ 2044년",
                ),
            ),
            expected_status="answered",
            expected_generation="llm",
            allowed_evidence_ids=("session:1",),
            required_evidence_ids=("session:1",),
            forbidden_evidence_ids=(),
            must_include_groups=(("2044년",),),
            must_not_include=("2050년",),
        ),
        PolicyGenerationEvalCase(
            id="fallback",
            category="insufficient_context",
            risk_tags=("fallback",),
            question="근거가 없으면?",
            demographics=demographics,
            evidence=(),
            expected_status="no_data",
            expected_generation="fallback",
            allowed_evidence_ids=(),
            required_evidence_ids=(),
            forbidden_evidence_ids=(),
            must_include_groups=(("답하기 어려워요",),),
            must_not_include=("보험금이 지급됩니다",),
        ),
    )

    def complete(_: str, user: str) -> dict[str, object]:
        payload = json.loads(user)
        question = str(payload["question"])
        if "근거가 없으면" in question:
            return {
                "confirmed_fact": "없는 근거로 답변합니다.",
                "guidance": None,
                "evidence_ids": ["session:999"],
                "suggestions": [],
                "limitations": [],
            }
        guidance = "반드시 가입하세요." if "어떻게 보면" in question else None
        return {
            "confirmed_fact": "보험기간은 2044년까지로 확인돼요.",
            "guidance": guidance,
            "evidence_ids": ["session:1"],
            "suggestions": [],
            "limitations": [],
        }

    report = evaluate_generation(cases, complete=complete)

    assert report.passed == report.total
    assert report.pass_rate == 1.0
    assert report.status_match_rate == 1.0
    assert report.required_evidence_coverage == 1.0
    assert "passed=" in render_report(report)


def test_policy_generation_eval_reports_contract_failures() -> None:
    case = PolicyGenerationEvalCase(
        id="case",
        category="evidence_selection",
        risk_tags=("citation_precision",),
        question="보험기간은?",
        demographics=load_generation_eval_cases()[0].demographics,
        evidence=load_generation_eval_cases()[0].evidence,
        expected_status="answered",
        expected_generation="llm",
        allowed_evidence_ids=("session:1",),
        required_evidence_ids=("session:1",),
        forbidden_evidence_ids=("session:2",),
        must_include_groups=(("2044년",),),
        must_not_include=("[전화번호]",),
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "다른 근거를 확인했어요.",
            "guidance": None,
            "evidence_ids": ["session:2"],
            "suggestions": [],
            "limitations": [],
        }

    report = evaluate_generation((case,), complete=complete)

    assert report.passed == 0
    assert report.results[0].failed_checks == (
        "allowed_evidence",
        "required_evidence",
        "forbidden_evidence",
        "must_include",
        "must_not_include",
    )
    assert "FAIL case" in render_report(report)


def test_policy_generation_eval_removes_injection_from_relevant_chunk() -> None:
    case = next(
        case
        for case in load_practice_eval_cases()
        if case.id == "challenge_injection_inside_relevant_chunk"
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "암진단비 금액을 확인했어요.",
            "guidance": None,
            "evidence_ids": ["session:2"],
            "suggestions": [],
            "limitations": [],
        }

    report = evaluate_generation((case,), complete=complete)

    assert report.passed == 1
    assert "암진단비 3,000만원" in report.results[0].answer
    assert "이전 지시" not in report.results[0].answer


def test_policy_generation_eval_checks_suggestions_for_forbidden_text() -> None:
    source = load_generation_eval_cases()[0]
    case = PolicyGenerationEvalCase(
        id="unsafe-suggestion",
        category=source.category,
        risk_tags=("sales_safety",),
        question="보장을 어떻게 준비할까?",
        demographics=source.demographics,
        evidence=source.evidence,
        expected_status="answered",
        expected_generation="llm",
        allowed_evidence_ids=("session:1",),
        required_evidence_ids=("session:1",),
        forbidden_evidence_ids=(),
        must_include_groups=(("보험기간",),),
        must_not_include=("다른 보험",),
    )

    def complete(_: str, __: str) -> dict[str, object]:
        return {
            "confirmed_fact": "보험기간을 확인했어요.",
            "guidance": None,
            "evidence_ids": ["session:1"],
            "suggestions": ["다른 보험도 확인해요."],
            "limitations": [],
        }

    report = evaluate_generation((case,), complete=complete)

    assert report.passed == 0
    assert report.results[0].failed_checks == ("must_not_include",)
    assert report.results[0].notes == ("forbidden answer terms present: 다른 보험",)


def test_policy_generation_eval_keeps_empty_explicit_case_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.rag.policy.evaluation.generation.load_generation_eval_cases",
        lambda: (_ for _ in ()).throw(AssertionError("fixture should not load")),
    )

    report = evaluate_generation((), complete=lambda _system, _user: {})

    assert report.total == 0
    assert report.passed == 0
    assert report.pass_rate == 0.0


def test_policy_generation_eval_requires_openai_key_for_live_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Settings:
        openai_api_key = ""

    monkeypatch.setattr(
        "app.services.rag.policy.evaluation.generation.get_settings",
        lambda: _Settings(),
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        evaluate_generation(())
