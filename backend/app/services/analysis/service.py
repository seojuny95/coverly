"""Grounded counselor-style analysis over structured portfolio facts."""

from collections import defaultdict
from functools import lru_cache
from typing import Literal

from app.schemas.analysis import (
    AnalysisContextAnswer,
    AnalysisSource,
    ClassificationAnalysis,
    CounselorAnalysis,
    CounselorInsight,
    CoverageGap,
    PortfolioAnalysisResponse,
)
from app.schemas.consultation import Gender, GenerationMode, InsuredDemographics
from app.schemas.portfolio import PolicyInput
from app.services.analysis.generation import generate_counselor
from app.services.coverage_knowledge.purpose import coverage_purpose
from app.services.coverage_knowledge.taxonomy import LifeStageCheck, check_life_stage
from app.services.evidence.catalog import (
    EvidenceCatalog,
    build_evidence_catalog,
    with_official_evidence,
)
from app.services.llm import JsonCompleter
from app.services.portfolio.demographics import resolve_portfolio_demographics
from app.services.portfolio.premium import summarize_premiums
from app.services.portfolio.summary import (
    PortfolioFacts,
    build_portfolio_facts,
    count_duplicate_indemnity_coverages,
)
from app.services.rag.official.models import RetrievalHit
from app.services.rag.official.retrieval import retrieve

_UNCLASSIFIED = "미분류"


def analyze_portfolio(
    policies: list[PolicyInput],
    *,
    demographics: InsuredDemographics | None = None,
    age: int | None = None,
    gender: Gender = "미상",
    complete: JsonCompleter | None = None,
    personal_context: tuple[AnalysisContextAnswer, ...] = (),
) -> PortfolioAnalysisResponse:
    """Combine deterministic facts with filtered LLM consultation copy."""

    requested = demographics
    if requested is None and (age is not None or gender != "미상"):
        requested = InsuredDemographics(age=age, gender=gender, source="user")
    insured = resolve_portfolio_demographics(policies, requested)
    facts = build_portfolio_facts(policies)
    life_stage_check = _life_stage_check(insured, facts)
    official_guidance = _official_analysis_guidance()
    catalog = with_official_evidence(
        build_evidence_catalog(facts, insured, life_stage_check.missing),
        official_guidance,
    )
    fallback = _fallback_counselor(facts, insured, life_stage_check, catalog)
    counselor, generation = generate_counselor(
        fallback,
        facts,
        insured,
        life_stage_check,
        catalog,
        complete,
        official_guidance=official_guidance,
        personal_context=personal_context,
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
        indemnity_coverage_count=len(summary.indemnity_coverages),
        indemnity_duplicate_count=count_duplicate_indemnity_coverages(summary),
        excluded_coverage_count=excluded_count,
        excluded_coverages=list(summary.excluded_coverages),
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
        premium=summarize_premiums(list(facts.policies)),
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
    held_label = ", ".join(life_stage_check.held[:3])
    missing_label = ", ".join(life_stage_check.missing[:3])
    overview_parts = [f"{profile} 기준으로 비자동차 보험 {len(facts.policies)}건을 살펴봤어요."]
    if held_label:
        overview_parts.append(
            f"업로드한 증권에서는 {held_label} 관련 담보의 가입 사실을 확인했어요."
        )
    if missing_label:
        overview_parts.append(
            f"반면 {missing_label} 관련 담보는 현재 올린 증권에서 찾지 못해 "
            "다른 증권도 확인할 필요가 있어요."
        )
    overview_parts.append(
        "확인되지 않은 항목은 보장이 없다는 뜻이 아니라, "
        "이번에 분석한 자료만으로는 확인하지 못했다는 의미예요."
    )
    overview = " ".join(overview_parts)
    strengths: list[CounselorInsight] = []
    for category in life_stage_check.held:
        evidence_ids = catalog.coverage_ids_by_category.get(category, ())
        if not evidence_ids:
            continue
        purpose = coverage_purpose(category)
        confirmed = "지금 증권에서 이 담보의 가입 사실을 확인했어요."
        detail = (
            f"{confirmed} 왜 의미가 있냐면, {purpose}"
            if purpose
            else f"{confirmed} 다만 가입 사실만으로 충분한 보장인지는 판단하지 않았어요."
        )
        strengths.append(
            CounselorInsight(
                title=f"{category} 담보가 확인돼요",
                detail=detail,
                evidence_ids=list(evidence_ids),
            )
        )

    gaps: list[CounselorInsight] = []
    gap_evidence = [item for item in catalog.items if item.id.startswith("gap:")]
    for category, evidence in zip(life_stage_check.missing, gap_evidence, strict=True):
        purpose = coverage_purpose(category)
        unconfirmed = "지금 증권에서는 이 성격의 보장이 확인되지 않았어요."
        detail = (
            f"{unconfirmed} 확인할 이유는 {purpose}"
            if purpose
            else f"{unconfirmed} 다른 증권에 있는지 확인해야 실제 공백인지 구분할 수 있어요."
        )
        gaps.append(
            CounselorInsight(
                title=f"{category} 항목을 확인해 보세요",
                detail=detail,
                evidence_ids=[evidence.id],
            )
        )

    return CounselorAnalysis(
        overview=overview,
        strengths=strengths,
        gaps=gaps,
        amount_review_items=[],
        next_questions=[
            "이번 분석에서 가장 먼저 알고 싶은 것은 무엇인가요?",
            "아직 올리지 않은 보험이 있나요?",
            "가족의 생활비를 책임지고 있나요?",
        ],
        next_steps=[
            "확인되지 않은 담보가 다른 증권에 있는지 먼저 점검해 보세요.",
            "원본 약관의 지급사유·면책 조건과 최신 계약 상태를 확인해 보세요.",
            "보상 조건과 면책은 해당 약관 원문을 추가로 확인해 주세요.",
        ],
    )


def _life_stage_check(demographics: InsuredDemographics, facts: PortfolioFacts) -> LifeStageCheck:
    if demographics.age is None:
        return LifeStageCheck(life_stage="미상", held=(), missing=())
    coverage_names = [coverage.담보명 for policy in facts.policies for coverage in policy.보장목록]
    if facts.coverage_summary.indemnity_coverages:
        coverage_names.append("실손의료")
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


@lru_cache(maxsize=1)
def _official_analysis_guidance() -> tuple[RetrievalHit, ...]:
    """Retrieve grounding hits for the counselor prompt.

    This is supplementary context, not a required fact — if pgvector isn't
    reachable (e.g. DATABASE_URL unset in this environment), degrade to no
    guidance instead of failing the whole analysis, same as explain.py's
    LLM-boundary degrade pattern.
    """
    try:
        return tuple(
            retrieve(
                "약관에서 지급사유 면책 감액 보상하지 않는 사항을 왜 확인해야 하는지",
                final_k=4,
            )
        )
    except Exception:
        return ()


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
