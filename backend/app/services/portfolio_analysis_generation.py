"""LLM generation and filtering for counselor-style portfolio analysis."""

import json

from pydantic import BaseModel, Field

from app.schemas.analysis import (
    AmountReviewItem,
    CounselorAnalysis,
    CounselorInsight,
)
from app.schemas.consultation import GenerationMode, InsuredDemographics
from app.services.coverage_taxonomy import LifeStageCheck, classify_coverage
from app.services.llm import JsonCompleter, structured_completer
from app.services.portfolio_consultation import (
    EvidenceCatalog,
    is_safe_confirmed_fact,
    is_safe_general_guidance,
    valid_evidence_ids,
)
from app.services.portfolio_summary import PortfolioFacts


class _LlmInsight(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class _LlmAmountReview(BaseModel):
    coverage_evidence_id: str


class _LlmCounselorDraft(BaseModel):
    strengths: list[_LlmInsight] = Field(default_factory=list, max_length=8)
    gaps: list[_LlmInsight] = Field(default_factory=list, max_length=8)
    amount_review_items: list[_LlmAmountReview] = Field(default_factory=list, max_length=8)
    next_questions: list[str] = Field(default_factory=list, max_length=6)
    next_steps: list[str] = Field(default_factory=list, max_length=6)


def generate_counselor(
    fallback: CounselorAnalysis,
    facts: PortfolioFacts,
    demographics: InsuredDemographics,
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
    complete: JsonCompleter | None,
) -> tuple[CounselorAnalysis, GenerationMode]:
    if not facts.policies:
        return fallback, "fallback"

    try:
        raw = (complete or structured_completer(_LlmCounselorDraft))(
            _system_prompt(),
            _user_prompt(demographics, life_stage_check, catalog),
        )
        draft = _LlmCounselorDraft.model_validate(raw)
    except Exception:
        return fallback, "fallback"

    strengths = _filter_insights(draft.strengths, catalog, evidence_prefix="coverage:")
    strengths.extend(_filter_insights(draft.strengths, catalog, evidence_prefix="indemnity:"))
    gaps = _filter_insights(draft.gaps, catalog, evidence_prefix="gap:")
    amount_reviews = _filter_amount_reviews(draft.amount_review_items, catalog)
    next_questions = _filter_guidance_list(draft.next_questions)
    next_steps = _filter_guidance_list(draft.next_steps)
    accepted_count = sum(
        len(items) for items in (strengths, gaps, amount_reviews, next_questions, next_steps)
    )
    if accepted_count == 0:
        return fallback, "fallback"

    return (
        CounselorAnalysis(
            overview=fallback.overview,
            strengths=strengths or fallback.strengths,
            gaps=gaps or fallback.gaps,
            amount_review_items=amount_reviews or fallback.amount_review_items,
            next_questions=next_questions or fallback.next_questions,
            next_steps=next_steps or fallback.next_steps,
        ),
        "llm",
    )


def _filter_insights(
    drafts: list[_LlmInsight],
    catalog: EvidenceCatalog,
    *,
    evidence_prefix: str,
) -> list[CounselorInsight]:
    insights: list[CounselorInsight] = []
    for draft in drafts:
        evidence_ids = valid_evidence_ids(draft.evidence_ids, catalog)
        if evidence_ids is None:
            continue
        if any(not evidence_id.startswith(evidence_prefix) for evidence_id in evidence_ids):
            continue
        if not is_safe_confirmed_fact(draft.title):
            continue
        if not is_safe_confirmed_fact(draft.detail):
            continue
        if not _insight_matches_evidence(draft, evidence_ids, catalog):
            continue
        insights.append(
            CounselorInsight(
                title=draft.title.strip(),
                detail=draft.detail.strip(),
                evidence_ids=list(evidence_ids),
            )
        )
    return insights


def _insight_matches_evidence(
    draft: _LlmInsight,
    evidence_ids: tuple[str, ...],
    catalog: EvidenceCatalog,
) -> bool:
    text = f"{draft.title} {draft.detail}"
    claimed_category = classify_coverage(text)
    for evidence_id in evidence_ids:
        coverage_name = catalog.by_id[evidence_id].coverage_name
        if not coverage_name:
            return False
        expected_category = classify_coverage(coverage_name)
        if expected_category is not None:
            if claimed_category != expected_category:
                return False
            continue
        normalized_name = "".join(coverage_name.split())
        if normalized_name not in "".join(text.split()):
            return False
    return True


def _filter_amount_reviews(
    drafts: list[_LlmAmountReview], catalog: EvidenceCatalog
) -> list[AmountReviewItem]:
    items: list[AmountReviewItem] = []
    used_evidence: set[str] = set()
    for draft in drafts:
        evidence = catalog.by_id.get(draft.coverage_evidence_id)
        if evidence is None or evidence.amount is None or evidence.coverage_name is None:
            continue
        if draft.coverage_evidence_id in used_evidence:
            continue
        used_evidence.add(draft.coverage_evidence_id)
        items.append(
            AmountReviewItem(
                coverage_name=evidence.coverage_name,
                current_amount=evidence.amount,
                title=f"{evidence.coverage_name} 금액은 개인 기준 검토가 필요해요",
                guidance=("현재 확인 금액과 나이·성별만으로는 적정성을 확정할 수 없습니다."),
                rationale=(
                    "소득, 치료·회복 기간 생활비, 부양 책임, 가용 예산과 함께 비교해야 합니다."
                ),
                suggested_range=None,
                confidence="low",
                required_context=[
                    "소득",
                    "치료·회복 기간 생활비",
                    "부양 책임",
                    "가용 예산",
                ],
                evidence_ids=[draft.coverage_evidence_id],
            )
        )
    return items


def _filter_guidance_list(items: list[str]) -> list[str]:
    accepted: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not is_safe_general_guidance(cleaned) or cleaned in accepted:
            continue
        accepted.append(cleaned)
    return accepted


def _system_prompt() -> str:
    return """당신은 보험 상담 전 사전 점검을 돕는 분석가입니다.
반드시 제공된 evidence id와 사실만 가입 사실로 사용하세요.
strengths와 gaps는 숫자를 쓰지 말고, 모든 항목에 유효한 evidence id를 붙이세요.
보상 가능 여부, 면책, 보험금 지급 조건은 판단하지 마세요.
amount_review_items의 현재 담보명과 금액은 직접 쓰지 말고 coverage evidence id만 고르세요.
amount_review_items에서는 검토할 coverage evidence id만 선택하세요.
금액 문구와 개인 변수 안내는 서버가 안전한 고정 템플릿으로 조립합니다.
제공되지 않은 개인 사실을 있다고 가정하지 말고 상품 가입을 지시하지 마세요."""


def _user_prompt(
    demographics: InsuredDemographics,
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
) -> str:
    payload = {
        "demographics": demographics.model_dump(mode="json"),
        "life_stage": life_stage_check.life_stage,
        "confirmed_categories": list(life_stage_check.held),
        "review_categories": list(life_stage_check.missing),
        "evidence": [item.model_dump(mode="json") for item in catalog.items],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
