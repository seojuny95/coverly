"""LLM overview copy for the portfolio summary screen."""

import logging
from typing import Literal, cast

from pydantic import BaseModel, Field

from app.integrations.openai.client import JsonCompleter, dump_prompt_json, structured_completer
from app.modules.portfolio.schemas import (
    EssentialCoverageItem,
    PortfolioCoverageSummary,
    PortfolioOverview,
    PortfolioOverviewTakeaway,
)
from app.modules.portfolio.summary import duplicate_actual_loss_coverage_names

logger = logging.getLogger(__name__)


class SummaryOverviewUnavailableError(RuntimeError):
    """Raised when the required LLM overview cannot be generated safely."""


type _OverviewTitle = Literal[
    "업로드한 증권의 확인 항목을 정리했어요",
    "확인된 내용과 다음 확인 항목을 함께 살펴봐요",
    "보험료와 보장 조건을 차례로 확인해요",
]
type _OverviewParagraph = Literal[
    "업로드한 증권에서 읽은 내용을 보험료, 보장 구성, 다음 확인 항목으로 나눠 정리했어요.",
    "이 총평은 업로드한 자료에서 확인한 내용을 바탕으로 한 1차 정리예요.",
    "월 보험료는 담보 구성과 갱신 여부, 납입 기간을 함께 확인해야 해요.",
    "현재 자료에서 확인되지 않은 항목은 다른 증권이나 특약명에서도 이어서 확인해보세요.",
    "확인 범위가 제한된 담보는 실제 보장 범위와 약관 조건을 이어서 확인해보세요.",
    "겹쳐 보이는 담보는 실제 지급 조건과 자기부담금 조건을 약관에서 확인해보세요.",
]

_BASE_OVERVIEW_PARAGRAPH: _OverviewParagraph = (
    "업로드한 증권에서 읽은 내용을 보험료, 보장 구성, 다음 확인 항목으로 나눠 정리했어요."
)
_LIMITATION_OVERVIEW_PARAGRAPH: _OverviewParagraph = (
    "이 총평은 업로드한 자료에서 확인한 내용을 바탕으로 한 1차 정리예요."
)
_PREMIUM_OVERVIEW_PARAGRAPH: _OverviewParagraph = (
    "월 보험료는 담보 구성과 갱신 여부, 납입 기간을 함께 확인해야 해요."
)
_MISSING_OVERVIEW_PARAGRAPH: _OverviewParagraph = (
    "현재 자료에서 확인되지 않은 항목은 다른 증권이나 특약명에서도 이어서 확인해보세요."
)
_TERMS_REVIEW_OVERVIEW_PARAGRAPH: _OverviewParagraph = (
    "확인 범위가 제한된 담보는 실제 보장 범위와 약관 조건을 이어서 확인해보세요."
)
_OVERLAP_OVERVIEW_PARAGRAPH: _OverviewParagraph = (
    "겹쳐 보이는 담보는 실제 지급 조건과 자기부담금 조건을 약관에서 확인해보세요."
)


class _LlmOverviewDraft(BaseModel):
    title: _OverviewTitle
    paragraphs: list[_OverviewParagraph] = Field(min_length=2, max_length=3)


def attach_summary_overview(
    summary: PortfolioCoverageSummary,
    complete: JsonCompleter | None = None,
) -> PortfolioCoverageSummary:
    """Attach LLM copy generated only from deterministic summary judgments."""

    overview = generate_summary_overview(summary, complete)
    if overview is None:
        raise SummaryOverviewUnavailableError("Portfolio overview generation failed")
    return summary.model_copy(update={"overview": overview})


def generate_summary_overview(
    summary: PortfolioCoverageSummary,
    complete: JsonCompleter | None = None,
) -> PortfolioOverview | None:
    if not summary.essential_coverage_check.items:
        return None

    judgments = _summary_judgments(summary)
    try:
        raw = (complete or structured_completer(_LlmOverviewDraft))(
            _system_prompt(),
            _user_prompt(_overview_prompt_facts(summary)),
        )
        draft = _LlmOverviewDraft.model_validate(raw)
    except Exception:
        logger.exception("portfolio_overview_generation_failed")
        return None

    allowed_paragraphs = _allowed_overview_paragraphs(summary)
    paragraphs = list(dict.fromkeys(draft.paragraphs))
    if len(paragraphs) < 2 or any(paragraph not in allowed_paragraphs for paragraph in paragraphs):
        return None

    takeaways = cast(list[dict[str, str]], judgments["takeaways"])
    return PortfolioOverview(
        generation="llm",
        title=draft.title,
        paragraphs=[str(paragraph) for paragraph in paragraphs],
        takeaways=[PortfolioOverviewTakeaway.model_validate(takeaway) for takeaway in takeaways],
    )


def _summary_judgments(summary: PortfolioCoverageSummary) -> dict[str, object]:
    items = summary.essential_coverage_check.items
    confirmed = [item for item in items if item.status != "not_found"]
    missing = [item for item in items if item.status == "not_found"]
    review = [item for item in items if item.status == "needs_review"]
    premium = _premium_judgment(summary, missing)
    duplicate_actual_loss_names = duplicate_actual_loss_coverage_names(summary)

    return {
        "premium": premium,
        "coverage": {
            "confirmed_count": len(confirmed),
            "total_core_count": len(items),
            "confirmed": _coverage_names(confirmed),
            "missing": _coverage_names(missing),
            "needs_review": _coverage_names(review),
            "duplicate_actual_loss_coverages": duplicate_actual_loss_names,
            "missing_diagnosis_count": len(
                [
                    item
                    for item in missing
                    if item.kind in {"cancer", "cerebrovascular", "ischemic_heart"}
                ]
            ),
        },
        "special_policies": [
            {
                "label": analysis.label,
                "policy_count": analysis.policy_count,
                "overview": analysis.overview,
            }
            for analysis in summary.special_policy_analyses
        ],
        "takeaways": _takeaways(
            summary,
            premium,
            confirmed,
            missing,
            review,
            duplicate_actual_loss_names,
        ),
        "limitations": [
            "업로드한 증권에서 읽은 담보명, 가입금액, 월 보험료 기준의 1차 해석",
            "실제 충분성은 소득, 부양가족, 대출, 병력, 약관의 면책·감액·갱신 조건 확인 필요",
            "현재 자료에서 찾지 못한 항목은 미가입 단정이 아니라 추가 확인 대상",
        ],
    }


def _overview_prompt_facts(summary: PortfolioCoverageSummary) -> dict[str, object]:
    """Expose facts needed for sentence selection without adequacy comparisons."""

    items = summary.essential_coverage_check.items
    missing = [item for item in items if item.status == "not_found"]
    review = [item for item in items if item.status == "needs_review"]
    return {
        "monthly_premium_confirmed": bool(
            summary.premium is not None and summary.premium.monthly_policy_count > 0
        ),
        "confirmed_in_uploaded_documents": [
            item.label for item in items if item.status != "not_found"
        ],
        "not_confirmed_in_current_materials": [item.label for item in missing],
        "needs_terms_review": [item.label for item in review],
        "has_overlapping_actual_loss_names": bool(duplicate_actual_loss_coverage_names(summary)),
        "limitations": [
            "업로드한 자료에서 확인한 내용만 사용",
            "현재 자료에서 확인되지 않은 항목을 실제 미가입으로 단정하지 않음",
        ],
    }


def _allowed_overview_paragraphs(
    summary: PortfolioCoverageSummary,
) -> set[_OverviewParagraph]:
    allowed: set[_OverviewParagraph] = {
        _BASE_OVERVIEW_PARAGRAPH,
        _LIMITATION_OVERVIEW_PARAGRAPH,
    }
    if summary.premium is not None and summary.premium.monthly_policy_count > 0:
        allowed.add(_PREMIUM_OVERVIEW_PARAGRAPH)
    if any(item.status == "not_found" for item in summary.essential_coverage_check.items):
        allowed.add(_MISSING_OVERVIEW_PARAGRAPH)
    if any(item.status == "needs_review" for item in summary.essential_coverage_check.items):
        allowed.add(_TERMS_REVIEW_OVERVIEW_PARAGRAPH)
    if duplicate_actual_loss_coverage_names(summary):
        allowed.add(_OVERLAP_OVERVIEW_PARAGRAPH)
    return allowed


def _premium_judgment(
    summary: PortfolioCoverageSummary,
    missing: list[EssentialCoverageItem],
) -> dict[str, object]:
    premium = summary.premium
    benchmark = summary.premium_benchmark
    if premium is None:
        return {"status": "unknown", "label": "보험료 확인 필요"}
    if benchmark is None or premium.monthly_policy_count < 1:
        return {
            "status": "unbenchmarked",
            "label": "보험료만 확인",
            "monthly_total": premium.monthly_total,
        }

    all_core_coverage_visible = len(missing) == 0
    tone: Literal["low", "high", "in_range"]
    if premium.monthly_total < benchmark.suggested_min_premium:
        tone = "low"
        if all_core_coverage_visible:
            label = "보험료와 보장 조건을 함께 확인해요"
            guidance = "핵심 보장이 보이는지와 갱신·면책 조건을 함께 확인해보세요."
        else:
            label = "미확인 핵심 보장을 확인해요"
            guidance = "현재 자료에서 찾지 못한 핵심 보장이 실제로 없는지 약관과 함께 확인해보세요."
    elif premium.monthly_total > benchmark.suggested_max_premium:
        tone = "high"
        label = "보험료 구성과 갱신 조건을 확인해요"
        guidance = "보험료에 포함된 담보, 갱신 여부, 납입 기간을 현재 자료와 함께 확인해보세요."
    else:
        tone = "in_range"
        if all_core_coverage_visible:
            label = "보험료와 보장 조건을 함께 확인해요"
            guidance = "일반 가이드와의 차이, 세부 약관 조건을 함께 확인해보세요."
        else:
            label = "미확인 핵심 보장을 확인해요"
            guidance = "현재 자료에서 찾지 못한 핵심 보장이 실제로 없는지 약관과 함께 확인해보세요."

    return {
        "status": tone,
        "label": label,
        "guidance": guidance,
        "all_core_coverage_visible": all_core_coverage_visible,
        "missing_core_labels": _joined_labels(missing) if missing else "",
        "monthly_total": premium.monthly_total,
        "benchmark_label": benchmark.age_band_label,
        "recommended_min": benchmark.suggested_min_premium,
        "recommended_max": benchmark.suggested_max_premium,
    }


def _takeaways(
    summary: PortfolioCoverageSummary,
    premium: dict[str, object],
    confirmed: list[EssentialCoverageItem],
    missing: list[EssentialCoverageItem],
    review: list[EssentialCoverageItem],
    duplicate_actual_loss_names: list[str],
) -> list[dict[str, str]]:
    return [
        {
            "label": "보험료",
            "title": str(premium.get("label", "보험료 확인 필요")),
            "detail": _premium_detail(premium),
        },
        {
            "label": "보장 구성",
            "title": f"{len(confirmed)}/{len(summary.essential_coverage_check.items)}개 확인",
            "detail": (
                f"{_joined_labels(missing)} 항목은 현재 자료에서 미확인이에요."
                if missing
                else "사망·3대 진단비·실손의료비 축이 모두 보여요."
            ),
        },
        {
            "label": "다음 확인",
            "title": (
                "중복 여부 확인"
                if duplicate_actual_loss_names
                else "보장 범위 확인"
                if review
                else "미확인 보장 확인"
                if missing
                else "약관 조건 확인"
            ),
            "detail": _next_detail(
                missing,
                review,
                duplicate_actual_loss_names,
            ),
        },
    ]


def _premium_detail(premium: dict[str, object]) -> str:
    total = premium.get("monthly_total")
    recommended_min = premium.get("recommended_min")
    recommended_max = premium.get("recommended_max")
    if not isinstance(total, int):
        return "월 보험료 자료가 부족해 적정성을 판단하기 어려워요."
    guidance = premium.get("guidance")
    if isinstance(guidance, str) and guidance:
        return guidance
    if not isinstance(recommended_min, int) or not isinstance(recommended_max, int):
        return f"{_format_won(total)}만 현재 자료에서 확인돼요."
    return f"권장 보험료는 {_format_won(recommended_min)}~{_format_won(recommended_max)}예요."


def _next_detail(
    missing: list[EssentialCoverageItem],
    review: list[EssentialCoverageItem],
    duplicate_actual_loss_names: list[str],
) -> str:
    if duplicate_actual_loss_names:
        names = " · ".join(duplicate_actual_loss_names)
        return f"{names} 실손형 담보의 중복 보상 제한 여부를 약관에서 확인해요."
    if review:
        return f"{_joined_labels(review)}의 실제 보장 범위와 약관 조건을 확인해요."
    if missing:
        return "다른 증권, 특약명, 가입설계서에 빠진 보장이 있는지 봐요."
    return "면책, 감액, 갱신, 자기부담금 조건을 약관에서 확인해요."


def _coverage_names(items: list[EssentialCoverageItem]) -> list[dict[str, object]]:
    return [
        {
            "kind": item.kind,
            "label": item.label,
            "status": item.status,
            "confirmed_amount": item.confirmed_amount,
            "coverage_count": item.coverage_count,
            "matched_coverage_names": item.matched_coverage_names,
        }
        for item in items
    ]


def _joined_labels(items: list[EssentialCoverageItem]) -> str:
    return " · ".join(item.label for item in items)


def _format_won(amount: int) -> str:
    return f"{amount:,}원"


def _system_prompt() -> str:
    return """너는 Coverly의 보험 분석 총평을 쓰는 상담사다.

해야 할 것:
- 입력 JSON의 판단값만 사용한다.
- 출력 스키마에 허용된 문장 중 입력 사실과 관련된 문장만 고른다.
- 보험료 확인 여부, 보장 확인 상태, 다음 확인 내용을 연결한다.
- 사용자가 올린 자료의 한계를 분명히 말한다.
- 해요체로 쓴다.

하지 말아야 할 것:
- 입력에 없는 가족관계, 소득, 병력, 상품명, 보험사 평가를 만들지 않는다.
- 새 상품 가입, 증액, 해지, 유지 같은 행동을 지시하지 않는다.
- 보험료나 보장을 높다/낮다, 충분하다/부족하다, 적정하다고 평가하지 않는다.
- 보험금 지급 여부나 약관상 보장 여부를 단정하지 않는다.
- 입력의 금액, 확인/미확인 상태, 판단 라벨을 바꾸지 않는다.

출력 규칙:
- title은 1문장.
- paragraphs는 2~3개 문단.
- 각 문단은 1~2문장.
"""


def _user_prompt(facts: dict[str, object]) -> str:
    return dump_prompt_json(
        {
            "task": "아래 확인 사실에 맞는 제목과 문단을 허용된 선택지에서 고르세요.",
            "facts": facts,
        }
    )
