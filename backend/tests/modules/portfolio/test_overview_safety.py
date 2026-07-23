import pytest

from app.modules.portfolio.overview import generate_summary_overview
from app.modules.portfolio.overview_safety import (
    OverviewCopySegment,
    overview_copy_is_safe,
)
from app.modules.portfolio.schemas import PolicyInput
from app.modules.portfolio.summary import summarize_portfolio_coverages


@pytest.mark.parametrize(
    ("title", "paragraph"),
    [
        ("암 진단비가 충분하게 준비됐어요", "현재 보장으로 충분해요."),
        ("암 진단비를 삼천만원으로 늘려야 해요", "보험금을 더 받으려면 증액해야 해요."),
        ("암 진단비 가입을 권해요", "지금 가입해야 해요."),
        ("암 진단비 가입을 추천해요", "암 진단비 가입을 추천해요."),
        ("암 진단비가 완벽하게 준비됐어요", "암 진단비가 든든하게 준비됐어요."),
        ("암 진단비가 확인됐어요", "암 진단비는 삼천만원으로 확인됐어요."),
    ],
)
def test_rejects_unsupported_judgments_and_actions(
    title: str,
    paragraph: str,
) -> None:
    assert not overview_copy_is_safe(
        title=title,
        title_slot_id="confirmed:summary",
        paragraphs=[
            OverviewCopySegment(
                slot_id="confirmed:summary",
                text=paragraph,
            )
        ],
        terms_by_slot={"confirmed:summary": frozenset({"암진단비"})},
    )


def test_rejects_a_fact_assigned_to_another_slot() -> None:
    assert not overview_copy_is_safe(
        title="암 진단비를 확인했어요",
        title_slot_id="confirmed:summary",
        paragraphs=[
            OverviewCopySegment(
                slot_id="unconfirmed:summary",
                text="암 진단비는 현재 자료에서 확인하지 못했어요.",
                limitation="현재 자료에서 찾지 못했을 뿐 미가입으로 단정하지 않아요.",
            )
        ],
        terms_by_slot={
            "confirmed:summary": frozenset({"암진단비"}),
            "unconfirmed:summary": frozenset({"뇌혈관진단비"}),
        },
    )


def test_generated_overview_retries_once_after_an_unsupported_claim() -> None:
    summary = summarize_portfolio_coverages(
        [
            PolicyInput.model_validate(
                {
                    "id": "p1",
                    "기본정보": {
                        "보험사": "보험사A",
                        "상품명": "상품A",
                        "보험분류": "제3보험",
                    },
                    "보장목록": [{"담보명": "암진단비", "지급유형": "정액"}],
                }
            )
        ]
    )
    calls = 0

    def complete(_system: str, user: str) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "title": "암 진단비가 충분하게 준비됐어요",
                "title_slot_id": "confirmed:summary",
                "paragraphs": [
                    {
                        "slot_id": "confirmed:summary",
                        "text": "현재 보장으로 충분해요.",
                    }
                ],
            }
        assert "안전 규칙" in user
        return {
            "title": "암 진단비를 현재 자료에서 확인했어요",
            "title_slot_id": "confirmed:summary",
            "paragraphs": [
                {
                    "slot_id": "confirmed:summary",
                    "text": "암 진단비는 현재 자료에서 확인된 보장이에요.",
                }
            ],
        }

    assert generate_summary_overview(summary, complete) is not None
    assert calls == 2
