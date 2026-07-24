import json

import pytest

from app.modules.portfolio.overview import (
    SummaryOverviewUnavailableError,
    attach_summary_overview,
    generate_summary_overview,
)
from app.modules.portfolio.schemas import (
    PolicyInput,
)
from app.modules.portfolio.summary import (
    duplicate_actual_loss_coverage_names,
    summarize_portfolio_coverages,
)


def _overview_draft(
    *,
    title: str = "확인된 보장과 살펴볼 조건을 함께 정리했어요",
    confirmed: bool = False,
    review: bool = False,
    unconfirmed: bool = False,
) -> dict[str, object]:
    groups = {
        "confirmed:summary": (
            confirmed,
            "현재 자료에서 확인된 보장의 역할을 함께 살펴봤어요.",
        ),
        "review:summary": (
            review,
            "확인된 보장 가운데 약관 조건을 더 살펴볼 내용이 있어요.",
        ),
        "unconfirmed:summary": (
            unconfirmed,
            "현재 자료에서 확인되지 않은 보장은 미가입으로 단정하지 않고 더 살펴봐요.",
        ),
    }
    paragraphs = [
        {
            "slot_id": slot_id,
            "text": text,
            **(
                {"limitation": "현재 자료에서 찾지 못했을 뿐 미가입으로 단정하지 않아요."}
                if slot_id == "unconfirmed:summary"
                else {}
            ),
        }
        for slot_id, (included, text) in groups.items()
        if included
    ]
    return {
        "title": title,
        "title_slot_id": paragraphs[0]["slot_id"],
        "paragraphs": paragraphs,
    }


def _policy(
    policy_id: str,
    category: str,
    insurer: str,
    coverages: list[dict[str, object]],
    tags: list[str] | None = None,
) -> PolicyInput:
    return PolicyInput.model_validate(
        {
            "id": policy_id,
            "기본정보": {
                "보험사": insurer,
                "상품명": f"상품-{policy_id}",
                "보험분류": category,
                "상품태그": tags or [],
            },
            "보장목록": coverages,
        }
    )


def test_summary_overview_uses_all_llm_generated_copy() -> None:
    policy = _policy(
        "p1",
        "건강보험",
        "보험사A",
        [
            {
                "담보명": "암진단비",
                "가입금액": "3천만원",
                "지급유형": "정액",
            }
        ],
    )
    summary = summarize_portfolio_coverages([policy])

    generated = _overview_draft(
        title="암 진단비와 아직 확인할 보장을 차분히 살펴봐요",
        confirmed=True,
        unconfirmed=True,
    )

    def complete(system: str, user: str) -> dict[str, object]:
        assert "# 역할" in system
        assert "# 하지 말아야 할 것" in system
        assert '"facts"' in user
        assert "confirmed_in_uploaded_documents" in user
        assert "explanation_basis" in user
        assert "paragraph_slots" in user
        assert "confirmed:summary" in user
        assert "well_prepared" not in user
        assert "takeaways" not in user
        assert "허용된 선택지" not in user
        return generated

    overview = generate_summary_overview(summary, complete)

    assert overview is not None
    assert overview.generation == "llm"
    assert overview.title == generated["title"]
    assert overview.paragraphs == [
        "현재 자료에서 확인된 보장의 역할을 함께 살펴봤어요.",
        (
            "현재 자료에서 확인되지 않은 보장은 미가입으로 단정하지 않고 더 살펴봐요. "
            "현재 자료에서 찾지 못했을 뿐 미가입으로 단정하지 않아요."
        ),
    ]


def test_summary_overview_failure_is_not_replaced_with_deterministic_copy() -> None:
    summary = summarize_portfolio_coverages(
        [_policy("p1", "건강보험", "보험사A", [{"담보명": "암진단비"}])]
    )

    def fail(_system: str, _user: str) -> dict[str, object]:
        raise RuntimeError("offline")

    with pytest.raises(SummaryOverviewUnavailableError):
        attach_summary_overview(summary, fail)


def test_summary_overview_keeps_limited_death_review_separate_from_overlap() -> None:
    summary = summarize_portfolio_coverages(
        [
            _policy(
                "p1",
                "건강보험",
                "보험사A",
                [{"담보명": "상해사망·후유장해 (20-100%) / 보통약관", "가입금액": "1억원"}],
            )
        ]
    )

    def complete(_system: str, user: str) -> dict[str, object]:
        assert '"multiple_contracts":false' in user
        assert '"observation":"confirmed_but_needs_terms_review"' in user
        return _overview_draft(
            review=True,
            unconfirmed=True,
        )

    overview = generate_summary_overview(summary, complete)

    assert overview is not None


def test_summary_overview_keeps_differently_named_medical_contracts_as_overlap() -> None:
    summary = summarize_portfolio_coverages(
        [
            _policy(
                "p1",
                "건강보험",
                "보험사A",
                [{"담보명": "질병실손의료비", "가입금액": "실손", "지급유형": "실손"}],
            ),
            _policy(
                "p2",
                "건강보험",
                "보험사B",
                [{"담보명": "상해실비", "가입금액": "실손", "지급유형": "실손"}],
            ),
        ]
    )

    def complete(_system: str, user: str) -> dict[str, object]:
        assert '"multiple_contracts":true' in user
        return _overview_draft(
            review=True,
            unconfirmed=True,
        )

    assert duplicate_actual_loss_coverage_names(summary) == []
    overview = generate_summary_overview(summary, complete)

    assert overview is not None


def test_summary_overview_rejects_blank_copy_after_whitespace_normalization() -> None:
    summary = summarize_portfolio_coverages(
        [_policy("p1", "건강보험", "보험사A", [{"담보명": "암진단비"}])]
    )

    def complete(_system: str, _user: str) -> dict[str, object]:
        return {
            "title": "     ",
            "title_slot_id": "confirmed:summary",
            "paragraphs": [{"slot_id": "confirmed:summary", "text": "          "}],
        }

    assert generate_summary_overview(summary, complete) is None


def test_summary_overview_rejects_fact_ids_under_the_wrong_role() -> None:
    summary = summarize_portfolio_coverages(
        [_policy("p1", "건강보험", "보험사A", [{"담보명": "암진단비"}])]
    )
    draft: dict[str, object] = {
        "title": "암 진단비와 아직 확인할 보장을 함께 살펴봐요",
        "title_slot_id": "confirmed:summary",
        "paragraphs": [
            {
                "slot_id": "review:summary",
                "text": "현재 자료에서 확인된 보장의 역할을 함께 살펴봤어요.",
            },
            {
                "slot_id": "unconfirmed:summary",
                "text": "현재 자료에서 확인되지 않은 보장은 미가입으로 단정하지 않아요.",
                "limitation": "현재 자료에서 찾지 못했을 뿐 미가입으로 단정하지 않아요.",
            },
        ],
    }

    assert generate_summary_overview(summary, lambda _system, _user: draft) is None


def test_summary_overview_does_not_fail_when_a_lower_priority_fact_is_omitted() -> None:
    summary = summarize_portfolio_coverages(
        [_policy("p1", "건강보험", "보험사A", [{"담보명": "암진단비"}])]
    )
    draft: dict[str, object] = {
        "title": "암 진단비가 현재 자료에서 확인됐어요",
        "title_slot_id": "confirmed:summary",
        "paragraphs": [
            {
                "slot_id": "confirmed:summary",
                "text": "암 진단비는 현재 자료에서 확인된 보장이에요.",
            }
        ],
    }

    assert generate_summary_overview(summary, lambda _system, _user: draft) is not None


def test_summary_overview_retries_once_when_fact_roles_are_invalid() -> None:
    summary = summarize_portfolio_coverages(
        [_policy("p1", "건강보험", "보험사A", [{"담보명": "암진단비"}])]
    )
    valid = _overview_draft(confirmed=True, unconfirmed=True)
    calls = 0

    def complete(_system: str, user: str) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "title": "암 진단비를 중심으로 보장을 살펴봐요",
                "title_slot_id": "confirmed:summary",
                "paragraphs": [
                    {
                        "slot_id": "review:summary",
                        "text": "암 진단비는 현재 자료에서 확인된 보장이에요.",
                    }
                ],
            }
        assert "previous_draft" in user
        return valid

    assert generate_summary_overview(summary, complete) is not None
    assert calls == 2


def test_summary_overview_receives_the_exact_duplicate_actual_loss_coverage() -> None:
    summary = summarize_portfolio_coverages(
        [
            _policy(
                "p1",
                "손해보험",
                "보험사A",
                [{"담보명": "자동차사고벌금(실손)", "지급유형": "실손"}],
                tags=["운전자보험"],
            ),
            _policy(
                "p2",
                "손해보험",
                "보험사B",
                [{"담보명": "자동차사고벌금(실손)", "지급유형": "실손"}],
                tags=["운전자보험"],
            ),
        ]
    )

    def complete(_system: str, user: str) -> dict[str, object]:
        payload = json.loads(user)
        facts = payload["facts"]["facts"]
        duplicate = next(fact for fact in facts if fact["fact_id"] == "actual_loss_duplicate:0")
        assert duplicate["coverage_name"] == "자동차사고벌금(실손)"
        assert duplicate["observation"] == "same_actual_loss_coverage_in_multiple_contracts"
        assert duplicate["payout_or_duplicate_benefit_confirmed"] is False
        return _overview_draft(
            review=True,
            unconfirmed=True,
        )

    assert generate_summary_overview(summary, complete) is not None
