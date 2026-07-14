"""Deterministic portfolio assessment calculations.

Reference map:
- premium burden: KOSIS household income/expenditure, KIRI premium spending study
- diagnosis living months: user living expense or KOSIS expenditure reference
- medical cost scenarios: NHIS disease inpatient cost, HIRA non-covered cost data
- death gap: KIRI mortality protection gap formula, KOSIS income/assets/debt data
- care cost scenarios: NHIS long-term care benefits and copay data

See docs/insurance-analysis-source-research.md for the Korean source review.
This module intentionally does not embed market averages or adequacy thresholds.
Official/statistical numbers must come in as versioned reference data so the
calculation layer stays auditable.
"""

from dataclasses import dataclass, field
from typing import Literal

from app.schemas.analysis import PremiumOverview
from app.services.portfolio.summary import PortfolioFacts, normalize_coverage_name

AssessmentTopic = Literal[
    "premium_burden",
    "diagnosis_living_months",
    "medical_cost_scenario",
    "death_protection_gap",
    "care_cost_scenario",
]
AssessmentStatus = Literal["calculated", "needs_context", "not_applicable"]
AssessmentConfidence = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class AssessmentContext:
    """User-provided inputs that materially change financial calculations."""

    monthly_income: int | None = None
    monthly_living_expense: int | None = None
    dependent_support_months: int | None = None
    debt: int | None = None
    assets: int | None = None


@dataclass(frozen=True)
class IncomeReference:
    monthly_income: int
    label: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class LivingExpenseReference:
    monthly_expense: int
    label: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class MedicalCostReference:
    topic: Literal["cancer", "brain", "heart"]
    label: str
    patient_cost: int
    non_covered_cost: int = 0
    source_ids: tuple[str, ...] = ()

    @property
    def total_cost(self) -> int:
        return self.patient_cost + self.non_covered_cost


@dataclass(frozen=True)
class CareCostReference:
    label: str
    monthly_total_cost: int
    public_copay_rate: float
    source_ids: tuple[str, ...]

    @property
    def monthly_user_cost(self) -> int:
        return round(self.monthly_total_cost * self.public_copay_rate)


@dataclass(frozen=True)
class AssessmentReferenceData:
    income: IncomeReference | None = None
    living_expense: LivingExpenseReference | None = None
    medical_costs: tuple[MedicalCostReference, ...] = ()
    care: CareCostReference | None = None


@dataclass(frozen=True)
class PortfolioAssessmentFinding:
    topic: AssessmentTopic
    status: AssessmentStatus
    title: str
    summary: str
    why: str
    calculation: str | None = None
    confidence: AssessmentConfidence = "low"
    evidence_ids: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    metrics: dict[str, int | float | str] = field(default_factory=dict)


def assess_portfolio_financials(
    facts: PortfolioFacts,
    premium: PremiumOverview,
    *,
    context: AssessmentContext,
    references: AssessmentReferenceData,
) -> tuple[PortfolioAssessmentFinding, ...]:
    """Return the five scoped assessment findings without LLM judgment."""

    totals = _coverage_totals_by_topic(facts)
    return (
        _assess_premium_burden(premium, context, references),
        _assess_diagnosis_living_months(totals, context, references),
        _assess_medical_cost(totals, references),
        _assess_death_gap(totals, context),
        _assess_care_cost(totals, references),
    )


def _assess_premium_burden(
    premium: PremiumOverview,
    context: AssessmentContext,
    references: AssessmentReferenceData,
) -> PortfolioAssessmentFinding:
    # Based on comparing confirmed monthly premium with user income first,
    # then with KOSIS/KIRI statistical income only as a fallback comparison.
    if premium.monthly_policy_count == 0:
        return PortfolioAssessmentFinding(
            topic="premium_burden",
            status="not_applicable",
            title="월 보험료를 계산할 수 없어요",
            summary="월납 보험료가 확인된 증권이 없어 보험료 부담률을 계산하지 않았어요.",
            why="보험료 부담은 실제 매달 나가는 금액이 확인돼야 소득이나 통계와 비교할 수 있어요.",
            required_context=("월납 보험료",),
        )

    if context.monthly_income:
        percent = premium.monthly_total / context.monthly_income * 100
        return PortfolioAssessmentFinding(
            topic="premium_burden",
            status="calculated",
            title="소득 대비 월 보험료 부담률",
            summary=f"확인된 월 보험료는 소득의 {_format_percent(percent)} 수준이에요.",
            why=(
                "여러 증권의 보험료를 합치면 매달 고정적으로 나가는 "
                "보험 비용을 한 번에 볼 수 있어요."
            ),
            calculation=(
                f"{_won(premium.monthly_total)} / {_won(context.monthly_income)}"
                f" = {_format_percent(percent)}"
            ),
            confidence="high",
            metrics={
                "monthly_premium": premium.monthly_total,
                "monthly_income": context.monthly_income,
                "burden_percent": round(percent, 1),
            },
        )

    if references.income:
        percent = premium.monthly_total / references.income.monthly_income * 100
        return PortfolioAssessmentFinding(
            topic="premium_burden",
            status="calculated",
            title="통계 소득 기준 보험료 부담률",
            summary=(
                f"개인 소득이 없어 {references.income.label}와 비교하면 "
                f"월 보험료는 {_format_percent(percent)} 수준이에요."
            ),
            why="개인 소득이 없을 때는 공식 통계를 참고해 대략적인 위치만 비교할 수 있어요.",
            calculation=(
                f"{_won(premium.monthly_total)} / {_won(references.income.monthly_income)}"
                f" = {_format_percent(percent)}"
            ),
            confidence="medium",
            evidence_ids=references.income.source_ids,
            metrics={
                "monthly_premium": premium.monthly_total,
                "reference_income": references.income.monthly_income,
                "burden_percent": round(percent, 1),
            },
        )

    return PortfolioAssessmentFinding(
        topic="premium_burden",
        status="needs_context",
        title="보험료 부담률은 소득 정보가 필요해요",
        summary="월 보험료 합계는 확인됐지만 비교할 소득 기준이 없어 부담률은 계산하지 않았어요.",
        why="같은 보험료라도 소득과 고정 지출에 따라 체감 부담이 크게 달라져요.",
        required_context=("월 소득",),
        metrics={"monthly_premium": premium.monthly_total},
    )


def _assess_diagnosis_living_months(
    totals: dict[str, int],
    context: AssessmentContext,
    references: AssessmentReferenceData,
) -> PortfolioAssessmentFinding:
    # Diagnosis benefits are treated as cash-buffer months, not as direct
    # medical-cost adequacy. Medical-cost comparison is handled separately.
    diagnosis_total = sum(totals[topic] for topic in ("cancer", "brain", "heart"))
    if diagnosis_total <= 0:
        return PortfolioAssessmentFinding(
            topic="diagnosis_living_months",
            status="not_applicable",
            title="주요 진단비가 확인되지 않았어요",
            summary="암·뇌·심장 진단비로 분류되는 정액 담보 금액을 찾지 못했어요.",
            why=(
                "진단비는 치료비 자체보다 진단 직후 생활비와 "
                "소득 공백을 버티는 목돈인지 보는 계산이 필요해요."
            ),
        )

    monthly_expense = context.monthly_living_expense
    source_ids: tuple[str, ...] = ()
    confidence: AssessmentConfidence = "high"
    label = "사용자 생활비"
    if monthly_expense is None and references.living_expense:
        monthly_expense = references.living_expense.monthly_expense
        source_ids = references.living_expense.source_ids
        confidence = "medium"
        label = references.living_expense.label

    if not monthly_expense:
        return PortfolioAssessmentFinding(
            topic="diagnosis_living_months",
            status="needs_context",
            title="진단비가 생활비 몇 달분인지 계산하려면 생활비가 필요해요",
            summary=f"주요 진단비 합계는 {_won(diagnosis_total)}로 확인됐어요.",
            why=(
                "진단비는 치료 중 소득이 줄거나 쉬어야 할 때 "
                "생활비를 몇 달 버티는지로 보면 이해하기 쉬워요."
            ),
            required_context=("월 생활비",),
            metrics={"diagnosis_total": diagnosis_total},
        )

    months = diagnosis_total / monthly_expense
    return PortfolioAssessmentFinding(
        topic="diagnosis_living_months",
        status="calculated",
        title="진단비의 생활비 대응 기간",
        summary=f"암·뇌·심장 진단비 합계는 {label} 기준 약 {_format_months(months)}분이에요.",
        why=(
            "흩어진 진단비를 합치면 치료 시작 시점의 생활비 공백을 "
            "어느 정도 흡수하는지 볼 수 있어요."
        ),
        calculation=f"{_won(diagnosis_total)} / {_won(monthly_expense)} = {_format_months(months)}",
        confidence=confidence,
        evidence_ids=source_ids,
        metrics={
            "diagnosis_total": diagnosis_total,
            "monthly_living_expense": monthly_expense,
            "covered_months": round(months, 1),
        },
    )


def _assess_medical_cost(
    totals: dict[str, int],
    references: AssessmentReferenceData,
) -> PortfolioAssessmentFinding:
    # Uses official disease-cost scenarios when available. The finding compares
    # confirmed coverage with reference costs, but does not declare adequacy.
    available = [
        reference
        for reference in references.medical_costs
        if totals[_reference_topic_key(reference.topic)] > 0
    ]
    if not available:
        return PortfolioAssessmentFinding(
            topic="medical_cost_scenario",
            status="needs_context",
            title="의료비 비교에는 질병별 참고 비용이 필요해요",
            summary=(
                "현재는 비교할 공식 치료비 시나리오가 연결되지 않아 "
                "의료비 대비 계산을 하지 않았어요."
            ),
            why=(
                "진단비 금액만 보면 충분해 보일 수 있지만, 실제 치료비와 "
                "비급여 부담은 질병·치료 방식별로 달라요."
            ),
            required_context=("질병별 공식 치료비 참조표",),
        )

    comparisons: list[str] = []
    source_ids: list[str] = []
    metrics: dict[str, int | float | str] = {}
    for reference in available:
        topic_key = _reference_topic_key(reference.topic)
        amount = totals[topic_key]
        difference = amount - reference.total_cost
        comparisons.append(
            f"{reference.label}: 보장 {_won(amount)} - 참고비용 {_won(reference.total_cost)}"
        )
        source_ids.extend(reference.source_ids)
        metrics[f"{reference.topic}_coverage"] = amount
        metrics[f"{reference.topic}_reference_cost"] = reference.total_cost
        metrics[f"{reference.topic}_difference"] = difference

    return PortfolioAssessmentFinding(
        topic="medical_cost_scenario",
        status="calculated",
        title="질병별 참고 의료비와 보장금액 비교",
        summary="확인된 진단비를 연결된 공식 의료비 시나리오와 나란히 비교했어요.",
        why=(
            "이 계산은 부족 여부를 단정하려는 것이 아니라, 진단비가 "
            "치료비·비급여·생활비 중 어디까지 설명되는지 나누어 보기 위한 거예요."
        ),
        calculation="; ".join(comparisons),
        confidence="medium",
        evidence_ids=tuple(dict.fromkeys(source_ids)),
        metrics=metrics,
    )


def _assess_death_gap(
    totals: dict[str, int],
    context: AssessmentContext,
) -> PortfolioAssessmentFinding:
    # Formula follows mortality protection gap research: family support need and
    # debt minus available assets and confirmed death coverage.
    death_total = totals["death"]
    if death_total <= 0:
        return PortfolioAssessmentFinding(
            topic="death_protection_gap",
            status="not_applicable",
            title="사망보장 금액이 확인되지 않았어요",
            summary="사망 담보로 분류되는 정액 보장금액을 찾지 못했어요.",
            why=(
                "사망보장은 본인 치료비보다 남은 가족의 생활비, 부채, "
                "보유 자산과 함께 계산해야 의미가 있어요."
            ),
        )

    missing = _missing_context(
        {
            "월 생활비": context.monthly_living_expense,
            "부양 기간": context.dependent_support_months,
            "부채": context.debt,
            "자산": context.assets,
        }
    )
    if missing:
        return PortfolioAssessmentFinding(
            topic="death_protection_gap",
            status="needs_context",
            title="사망보장은 가족 생활비와 부채 정보가 있어야 계산돼요",
            summary=f"확인된 사망보장 합계는 {_won(death_total)}예요.",
            why=(
                "사망보장 계산은 정해진 평균보다 남은 가족이 얼마 동안 "
                "어떤 비용을 감당해야 하는지가 핵심이에요."
            ),
            calculation="필요액 = 월 생활비 × 부양 기간 + 부채 - 자산 - 사망보장",
            required_context=missing,
            metrics={"death_coverage": death_total},
        )

    monthly_living = context.monthly_living_expense or 0
    support_months = context.dependent_support_months or 0
    debt = context.debt or 0
    assets = context.assets or 0
    need_before_insurance = monthly_living * support_months + debt - assets
    gap = need_before_insurance - death_total
    return PortfolioAssessmentFinding(
        topic="death_protection_gap",
        status="calculated",
        title="사망보장 필요액 시나리오",
        summary=f"입력한 가족 생활비 기준으로 계산한 사망보장 차이는 {_won(gap)}예요.",
        why=(
            "여러 보험의 사망보장을 합쳐야 가족 생활비와 부채를 "
            "실제로 얼마나 상쇄하는지 볼 수 있어요."
        ),
        calculation=(
            f"{_won(monthly_living)} × {support_months}개월 + {_won(debt)}"
            f" - {_won(assets)} - {_won(death_total)} = {_won(gap)}"
        ),
        confidence="high",
        metrics={
            "death_coverage": death_total,
            "need_before_insurance": need_before_insurance,
            "death_gap": gap,
        },
    )


def _assess_care_cost(
    totals: dict[str, int],
    references: AssessmentReferenceData,
) -> PortfolioAssessmentFinding:
    # Care coverage is compared with the remaining user-side cost after public
    # long-term care support, not with the full gross care-service price.
    care_total = totals["care"]
    if care_total <= 0:
        return PortfolioAssessmentFinding(
            topic="care_cost_scenario",
            status="not_applicable",
            title="간병 보장금액이 확인되지 않았어요",
            summary="간병·요양 담보로 분류되는 정액 보장금액을 찾지 못했어요.",
            why=(
                "간병은 치료비와 달리 장기간 반복 지출이 될 수 있어 "
                "공적 장기요양 지원 후 남는 본인 부담을 따로 봐야 해요."
            ),
        )
    if references.care is None:
        return PortfolioAssessmentFinding(
            topic="care_cost_scenario",
            status="needs_context",
            title="간병 분석에는 장기요양 비용 참조표가 필요해요",
            summary=f"확인된 간병 보장금액은 {_won(care_total)}예요.",
            why=(
                "간병비는 재가·시설·비급여 여부에 따라 달라서 "
                "공적 지원 후 본인 부담 기준이 연결돼야 해요."
            ),
            required_context=("장기요양 비용 참조표",),
            metrics={"care_coverage": care_total},
        )

    monthly_user_cost = references.care.monthly_user_cost
    months = care_total / monthly_user_cost if monthly_user_cost else 0
    return PortfolioAssessmentFinding(
        topic="care_cost_scenario",
        status="calculated",
        title="간병비 본인부담 시나리오",
        summary=(
            f"{references.care.label} 기준으로 간병 보장은 약 {_format_months(months)}분이에요."
        ),
        why=(
            "간병 담보는 가입금액 자체보다 공적 장기요양이 부담하지 않는 "
            "남은 비용을 몇 달 감당하는지로 보면 이해하기 쉬워요."
        ),
        calculation=(
            f"{_won(care_total)} / "
            f"({_won(references.care.monthly_total_cost)} × "
            f"{_format_percent(references.care.public_copay_rate * 100)})"
            f" = {_format_months(months)}"
        ),
        confidence="medium",
        evidence_ids=references.care.source_ids,
        metrics={
            "care_coverage": care_total,
            "monthly_user_cost": monthly_user_cost,
            "covered_months": round(months, 1),
        },
    )


def _coverage_totals_by_topic(facts: PortfolioFacts) -> dict[str, int]:
    totals = {
        "cancer": 0,
        "brain": 0,
        "heart": 0,
        "death": 0,
        "care": 0,
    }
    for item in facts.coverage_summary.totals:
        text = normalize_coverage_name(f"{item.display_name} {item.major_category}")
        if "암" in text or "악성신생물" in text:
            totals["cancer"] += item.total_amount
        if "뇌" in text:
            totals["brain"] += item.total_amount
        if "심장" in text or "심질환" in text or "허혈성" in text:
            totals["heart"] += item.total_amount
        if "사망" in text:
            totals["death"] += item.total_amount
        if "간병" in text or "요양" in text:
            totals["care"] += item.total_amount
    return totals


def _reference_topic_key(topic: Literal["cancer", "brain", "heart"]) -> str:
    return topic


def _missing_context(values: dict[str, object | None]) -> tuple[str, ...]:
    return tuple(label for label, value in values.items() if value is None)


def _won(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{abs(amount):,}원"


def _format_percent(value: float) -> str:
    return f"{value:.1f}%"


def _format_months(value: float) -> str:
    return f"{value:.1f}개월"
