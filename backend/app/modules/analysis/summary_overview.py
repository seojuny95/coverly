"""LLM overview copy for the portfolio summary screen."""

import logging
from typing import Literal, cast

from pydantic import BaseModel, Field

from app.integrations.openai.client import JsonCompleter, dump_prompt_json, structured_completer
from app.modules.evidence.catalog import is_safe_analysis_text
from app.modules.portfolio.schemas import (
    EssentialCoverageItem,
    PortfolioCoverageSummary,
    PortfolioOverview,
    PortfolioOverviewTakeaway,
)

logger = logging.getLogger(__name__)


class SummaryOverviewUnavailableError(RuntimeError):
    """Raised when the required LLM overview cannot be generated safely."""


class _LlmOverviewDraft(BaseModel):
    title: str = Field(max_length=80)
    paragraphs: list[str] = Field(min_length=2, max_length=3)


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
            _user_prompt(judgments),
        )
        draft = _LlmOverviewDraft.model_validate(raw)
    except Exception:
        logger.exception("portfolio_overview_generation_failed")
        return None

    title = draft.title.strip()
    paragraphs = [
        paragraph.strip() for paragraph in draft.paragraphs if is_safe_analysis_text(paragraph)
    ][:3]
    if not title or not is_safe_analysis_text(title) or len(paragraphs) < 2:
        return None

    takeaways = cast(list[dict[str, str]], judgments["takeaways"])
    return PortfolioOverview(
        generation="llm",
        title=title,
        paragraphs=paragraphs,
        takeaways=[PortfolioOverviewTakeaway.model_validate(takeaway) for takeaway in takeaways],
    )


def _summary_judgments(summary: PortfolioCoverageSummary) -> dict[str, object]:
    items = summary.essential_coverage_check.items
    confirmed = [item for item in items if item.status != "not_found"]
    missing = [item for item in items if item.status == "not_found"]
    review = [item for item in items if item.status == "needs_review"]
    premium = _premium_judgment(summary, missing)

    return {
        "premium": premium,
        "coverage": {
            "confirmed_count": len(confirmed),
            "total_core_count": len(items),
            "confirmed": _coverage_names(confirmed),
            "missing": _coverage_names(missing),
            "needs_review": _coverage_names(review),
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
        "takeaways": _takeaways(summary, premium, confirmed, missing, review),
        "limitations": [
            "업로드한 증권에서 읽은 담보명, 가입금액, 월 보험료 기준의 1차 해석",
            "실제 충분성은 소득, 부양가족, 대출, 병력, 약관의 면책·감액·갱신 조건 확인 필요",
            "현재 자료에서 찾지 못한 항목은 미가입 단정이 아니라 추가 확인 대상",
        ],
    }


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
            label = "현재 보험료는 좋아보여요"
            guidance = "핵심 보장이 보인다면 보험료가 낮은 것 자체는 좋은 신호예요."
        else:
            label = "권장보험을 점검해보세요"
            guidance = (
                "보험료가 낮은 이유가 핵심 보장 공백일 수 있으니 권장보험 항목을 먼저 점검해보세요."
            )
    elif premium.monthly_total > benchmark.suggested_max_premium:
        tone = "high"
        label = "현재 보험료는 높아보여요"
        guidance = "보험료가 과할 수 있으니 가입한 보험과 보장내용을 다시 확인해보세요."
    else:
        tone = "in_range"
        if all_core_coverage_visible:
            label = "현재 보험료는 좋아보여요"
            guidance = "권장 구간 안에서 핵심 보장도 보여요. 세부 약관 조건만 확인해요."
        else:
            label = "권장보험을 점검해보세요"
            guidance = "보험료는 권장 구간이어도 미확인 권장보험이 있으니 보장 구성을 점검해보세요."

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
                "중복 여부 확인" if review else "미확인 보장 확인" if missing else "약관 조건 확인"
            ),
            "detail": _next_detail(missing, review),
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
) -> str:
    if review:
        return f"{_joined_labels(review)}의 중복 가입과 실제 보장 범위를 확인해요."
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
- 보험료 판단, 보장 구성, 다음 확인 내용을 자연스러운 한국어로 연결한다.
- 보험료는 금액 단독으로 좋다/나쁘다 판단하지 말고 premium.guidance와 보장 확인 상태를 함께 따른다.
- 사용자가 올린 자료의 한계를 분명히 말한다.
- 해요체로 쓴다.

하지 말아야 할 것:
- 입력에 없는 가족관계, 소득, 병력, 상품명, 보험사 평가를 만들지 않는다.
- 새 상품 가입, 증액, 해지, 유지 같은 행동을 지시하지 않는다.
- 보험금 지급 여부나 약관상 보장 여부를 단정하지 않는다.
- 입력의 금액, 확인/미확인 상태, 판단 라벨을 바꾸지 않는다.

출력 규칙:
- title은 1문장.
- paragraphs는 2~3개 문단.
- 각 문단은 1~2문장.
"""


def _user_prompt(judgments: dict[str, object]) -> str:
    return dump_prompt_json(
        {
            "task": "아래 결정적 판단값을 바탕으로 전체 보험 총평의 제목과 문단을 작성하세요.",
            "judgments": judgments,
        }
    )
