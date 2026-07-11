"""Grounded counselor-style analysis over structured portfolio facts."""

from collections import defaultdict
from typing import Literal

from app.schemas.analysis import (
    AmountReviewItem,
    AnalysisSource,
    ClassificationAnalysis,
    CounselorAnalysis,
    CounselorInsight,
    CoverageGap,
    PortfolioAnalysisResponse,
)
from app.schemas.consultation import Gender, GenerationMode, InsuredDemographics
from app.schemas.portfolio import PolicyInput
from app.services.coverage_taxonomy import LifeStageCheck, check_life_stage
from app.services.llm import JsonCompleter
from app.services.portfolio_analysis_generation import generate_counselor
from app.services.portfolio_consultation import (
    EvidenceCatalog,
    build_evidence_catalog,
)
from app.services.portfolio_demographics import resolve_portfolio_demographics
from app.services.portfolio_summary import PortfolioFacts, build_portfolio_facts

_UNCLASSIFIED = "미분류"


def analyze_portfolio(
    policies: list[PolicyInput],
    *,
    demographics: InsuredDemographics | None = None,
    age: int | None = None,
    gender: Gender = "미상",
    complete: JsonCompleter | None = None,
) -> PortfolioAnalysisResponse:
    """Combine deterministic facts with filtered LLM consultation copy."""

    requested = demographics
    if requested is None and (age is not None or gender != "미상"):
        requested = InsuredDemographics(age=age, gender=gender, source="user")
    insured = resolve_portfolio_demographics(policies, requested)
    facts = build_portfolio_facts(policies)
    life_stage_check = _life_stage_check(insured, facts)
    catalog = build_evidence_catalog(facts, insured, life_stage_check.missing)
    fallback = _fallback_counselor(facts, insured, life_stage_check, catalog)
    counselor, generation = generate_counselor(
        fallback,
        facts,
        insured,
        life_stage_check,
        catalog,
        complete,
    )

    classifications = _analyze_classifications(facts)
    summary = facts.coverage_summary
    excluded_count = len(summary.excluded_coverages)
    notices = _analysis_notices(facts, insured)
    limitations = _analysis_limitations(generation)

    return PortfolioAnalysisResponse(
        status=_analysis_status(facts),
        policy_count=len(facts.policies),
        classification_count=len(classifications),
        confirmed_total_count=len(summary.totals),
        confirmed_total_amount=sum(item.total_amount for item in summary.totals),
        indemnity_coverage_count=len(summary.indemnity_coverages),
        excluded_coverage_count=excluded_count,
        excluded_auto_policy_count=summary.excluded_auto_policy_count,
        age=insured.age,
        gender=insured.gender,
        life_stage=life_stage_check.life_stage,
        demographics=insured,
        prepared_coverages=list(life_stage_check.held),
        coverage_gaps=[
            CoverageGap(
                category=category,
                reason="현재 업로드된 비자동차 증권에서 해당 담보를 확인하지 못했어요.",
            )
            for category in life_stage_check.missing
        ],
        baseline_notice=(
            "확인된 가입 사실과 일반적인 검토 가이드를 구분해 보여드려요. "
            "금액 범위와 우선순위는 공식 기준이나 가입 권유가 아닌 참고용 검토 제안입니다."
        ),
        classifications=classifications,
        sources=[_source(policy) for policy in facts.policies],
        counselor=counselor,
        evidence=list(catalog.items),
        notices=notices,
        limitations=limitations,
        generation=generation,
    )


def _fallback_counselor(
    facts: PortfolioFacts,
    demographics: InsuredDemographics,
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
) -> CounselorAnalysis:
    if not facts.policies:
        return CounselorAnalysis(
            overview=(
                "분석할 비자동차 보험이 아직 없어요. "
                "증권을 올리면 함께 살펴볼 항목을 정리해드릴게요."
            ),
            strengths=[],
            gaps=[],
            amount_review_items=[],
            next_questions=["분석할 보험증권을 먼저 업로드해 주세요."],
            next_steps=["증권 업로드 후 보험 분석 탭을 다시 열어 주세요."],
        )

    profile = _profile_label(demographics)
    overview = (
        f"{profile} 기준으로 비자동차 보험 {len(facts.policies)}건을 당신 편에서 살펴봤어요. "
        "확인된 보장과 추가로 점검할 항목을 나눠 정리했습니다."
    )
    strengths: list[CounselorInsight] = []
    for category in life_stage_check.held:
        evidence_ids = catalog.coverage_ids_by_category.get(category, ())
        if not evidence_ids:
            continue
        strengths.append(
            CounselorInsight(
                title=f"{category} 담보가 확인돼요",
                detail="현재 업로드된 증권에서 해당 담보의 가입 사실을 확인했습니다.",
                evidence_ids=list(evidence_ids),
            )
        )

    gaps: list[CounselorInsight] = []
    gap_evidence = [item for item in catalog.items if item.id.startswith("gap:")]
    for category, evidence in zip(life_stage_check.missing, gap_evidence, strict=True):
        gaps.append(
            CounselorInsight(
                title=f"{category} 항목을 확인해 보세요",
                detail=(
                    "현재 증권에서는 확인되지 않았어요. 필요 여부는 건강 상태, 예산, "
                    "기존 자산을 함께 놓고 살펴보는 것이 좋아요."
                ),
                evidence_ids=[evidence.id],
            )
        )

    amount_reviews: list[AmountReviewItem] = []
    for evidence in catalog.items:
        if evidence.amount is None or evidence.coverage_name is None:
            continue
        amount_reviews.append(
            AmountReviewItem(
                coverage_name=evidence.coverage_name,
                current_amount=evidence.amount,
                title=f"{evidence.coverage_name} 금액을 개인 기준과 비교해 보세요",
                guidance=(
                    "현재 금액은 확인됐지만 적정 금액은 소득, 치료 중 생활비, "
                    "부양 책임과 가용 예산을 함께 봐야 합니다."
                ),
                rationale=(
                    "증권만으로는 개인별 필요 금액을 확정할 수 없어 검토 항목으로 분류했어요."
                ),
                suggested_range=None,
                confidence="low",
                required_context=[
                    "소득",
                    "치료·회복 기간 생활비",
                    "부양 책임",
                    "가용 예산",
                ],
                evidence_ids=[evidence.id],
            )
        )

    return CounselorAnalysis(
        overview=overview,
        strengths=strengths,
        gaps=gaps,
        amount_review_items=amount_reviews,
        next_questions=[
            "치료나 회복 기간에 매달 꼭 필요한 생활비는 얼마인가요?",
            "가족을 위해 유지해야 할 소득과 부양 책임이 있나요?",
            "보험료로 무리 없이 유지할 수 있는 월 예산은 어느 정도인가요?",
        ],
        next_steps=[
            "확인되지 않은 담보가 다른 증권에 있는지 먼저 점검해 보세요.",
            "현재 가입금액을 소득·생활비·부양 책임과 함께 비교해 보세요.",
            "보상 조건과 면책은 해당 약관 원문을 추가로 확인해 주세요.",
        ],
    )


def _life_stage_check(demographics: InsuredDemographics, facts: PortfolioFacts) -> LifeStageCheck:
    if demographics.age is None:
        return LifeStageCheck(life_stage="미상", held=(), missing=())
    coverage_names = [coverage.담보명 for policy in facts.policies for coverage in policy.보장목록]
    return check_life_stage(demographics.age, coverage_names)


def _profile_label(demographics: InsuredDemographics) -> str:
    parts: list[str] = []
    if demographics.age is not None:
        parts.append(f"{demographics.age}세")
    if demographics.gender != "미상":
        parts.append(demographics.gender)
    return " · ".join(parts) if parts else "피보험자 정보 미확인"


def _analysis_notices(facts: PortfolioFacts, demographics: InsuredDemographics) -> list[str]:
    summary = facts.coverage_summary
    notices: list[str] = []
    if summary.excluded_coverages:
        notices.append("일부 담보는 지급유형 또는 금액을 확인할 수 없어 합계에서 제외했습니다.")
    if summary.indemnity_coverages:
        notices.append("실손형 담보는 가입금액 합산 대상이 아니며 보유 건수만 표시합니다.")
    if summary.excluded_auto_policy_count:
        notices.append("자동차 보험은 별도 분석 대상이므로 현재 포트폴리오 분석에서 제외했습니다.")
    if demographics.status == "conflict":
        notices.append("증권별 피보험자 나이 또는 성별이 서로 달라 개인화 분석에서 제외했습니다.")
    if demographics.status == "conflict_user_override":
        notices.append("증권별 피보험자 정보가 서로 달라 사용자가 확인한 정보로 분석했습니다.")
    return notices


def _analysis_limitations(generation: GenerationMode) -> list[str]:
    limitations = [
        "가입 사실은 업로드된 증권의 구조화 정보에서 확인된 범위만 사용했습니다.",
        "금액 검토 제안은 공식 적정성 기준이나 가입 권유가 아닌 일반 가이드입니다.",
        "보상 조건·면책·지급 가능성은 약관 근거가 없어 판단하지 않습니다.",
    ]
    if generation == "fallback":
        limitations.append(
            "AI 분석을 사용할 수 없어 확인된 사실 기반의 기본 점검 결과를 표시합니다."
        )
    return limitations


def _analyze_classifications(facts: PortfolioFacts) -> list[ClassificationAnalysis]:
    policies_by_classification: dict[str, list[PolicyInput]] = defaultdict(list)
    for policy in facts.policies:
        classification = policy.기본정보.보험분류 or _UNCLASSIFIED
        policies_by_classification[classification].append(policy)

    results: list[ClassificationAnalysis] = []
    for classification, policies in sorted(policies_by_classification.items()):
        class_facts = build_portfolio_facts(policies).coverage_summary
        results.append(
            ClassificationAnalysis(
                classification=classification,
                policy_count=len(policies),
                confirmed_total_count=len(class_facts.totals),
                confirmed_total_amount=sum(item.total_amount for item in class_facts.totals),
                indemnity_coverage_count=len(class_facts.indemnity_coverages),
                excluded_coverage_count=len(class_facts.excluded_coverages),
            )
        )
    return results


def _analysis_status(facts: PortfolioFacts) -> Literal["complete", "partial", "empty"]:
    if not facts.policies:
        return "empty"
    if facts.coverage_summary.excluded_coverages or any(
        policy.분석상태 == "부분" for policy in facts.policies
    ):
        return "partial"
    return "complete"


def _source(policy: PolicyInput) -> AnalysisSource:
    return AnalysisSource(
        policy_id=policy.id,
        insurer=policy.기본정보.보험사,
        product_name=policy.기본정보.상품명,
    )
