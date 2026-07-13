"""LLM generation and filtering for counselor-style portfolio analysis."""

from pydantic import BaseModel, Field

from app.schemas.analysis import (
    AmountReviewItem,
    CounselorAnalysis,
    CounselorInsight,
)
from app.schemas.consultation import GenerationMode, InsuredDemographics
from app.services.coverage_knowledge.purpose import coverage_purpose
from app.services.coverage_knowledge.taxonomy import LifeStageCheck, classify_coverage
from app.services.evidence.catalog import (
    EvidenceCatalog,
    filter_safe_unique_texts,
    is_safe_analysis_text,
    is_safe_general_guidance,
    valid_evidence_ids,
)
from app.services.llm import (
    JsonCompleter,
    compact_prompt_text,
    dump_prompt_json,
    structured_completer,
)
from app.services.portfolio.premium import summarize_premiums
from app.services.portfolio.summary import (
    PortfolioFacts,
    count_duplicate_indemnity_coverages,
)
from app.services.rag.models import RetrievalHit

# Strengths cite held coverages; gaps may also cite existing coverages/실손 to
# flag over-insurance, not only missing (gap:) categories.
_STRENGTH_PREFIXES = ("coverage:", "indemnity:")
_GAP_PREFIXES = ("gap:", "coverage:", "indemnity:", "excluded:")


class _LlmInsight(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class _LlmAmountReview(BaseModel):
    coverage_evidence_id: str


class _LlmCounselorDraft(BaseModel):
    overview: str = Field(default="", max_length=600)
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
    *,
    official_guidance: tuple[RetrievalHit, ...] = (),
) -> tuple[CounselorAnalysis, GenerationMode]:
    if not facts.policies:
        return fallback, "fallback"

    try:
        raw = (complete or structured_completer(_LlmCounselorDraft))(
            _system_prompt(),
            _user_prompt(demographics, life_stage_check, catalog, facts, official_guidance),
        )
        draft = _LlmCounselorDraft.model_validate(raw)
    except Exception:
        return fallback, "fallback"

    strengths = _filter_insights(draft.strengths, catalog, allowed_prefixes=_STRENGTH_PREFIXES)
    gaps = _filter_insights(draft.gaps, catalog, allowed_prefixes=_GAP_PREFIXES)
    amount_reviews = _filter_amount_reviews(draft.amount_review_items, catalog)
    next_questions = filter_safe_unique_texts(
        draft.next_questions,
        is_safe=is_safe_general_guidance,
    )
    next_steps = filter_safe_unique_texts(
        draft.next_steps,
        is_safe=is_safe_general_guidance,
    )
    accepted_count = sum(
        len(items) for items in (strengths, gaps, amount_reviews, next_questions, next_steps)
    )
    if accepted_count == 0:
        return fallback, "fallback"

    overview = draft.overview.strip()
    if not overview or not is_safe_analysis_text(overview):
        overview = fallback.overview

    return (
        CounselorAnalysis(
            overview=overview,
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
    allowed_prefixes: tuple[str, ...],
) -> list[CounselorInsight]:
    insights: list[CounselorInsight] = []
    for draft in drafts:
        evidence_ids = valid_evidence_ids(draft.evidence_ids, catalog)
        if evidence_ids is None:
            continue
        if any(not evidence_id.startswith(allowed_prefixes) for evidence_id in evidence_ids):
            continue
        if not is_safe_analysis_text(draft.title):
            continue
        if not is_safe_analysis_text(draft.detail):
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
    """Keep each insight on the topic of what it cites, so amounts and opinions
    attach to the right coverage instead of a mislabeled one."""

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


def _system_prompt() -> str:
    return (
        "당신은 사용자의 편에서 이미 가입한 보험을 함께 살펴보는 보험 상담 분석가입니다.\n"
        "목표는 지금 가입한 보험을 최대한 깊이 분석해, 왜 잘 가입돼 있는지(strengths)와 "
        "무엇이 과하거나 부족한지(gaps)를 근거와 함께 짚는 것입니다.\n\n"
        "사용할 근거:\n"
        "- 제공된 evidence의 담보명·금액·건수, category_purposes(담보가 대비하는 상황), "
        "monthly_premium_total, duplicate_indemnity_count만 사실로 쓰세요.\n"
        "- official_guidance는 약관에서 지급사유·면책·감액·보상하지 않는 사항을 왜 "
        "확인해야 하는지 설명할 때만 쓰세요. 이것으로 strengths/gaps/금액 판단을 "
        "새로 만들거나 바꾸지 마세요.\n"
        "- 없는 담보·숫자를 지어내지 말고, 인용한 모든 항목에 "
        "실제 존재하는 evidence id를 붙이세요.\n"
        "- 각 strengths/gaps 항목은 자신이 인용한 evidence의 담보와 같은 주제여야 합니다.\n\n"
        "strengths(현재 강점): 확인된 담보가 그 담보가 대비하는 상황과 금액을 기준으로 "
        "왜 잘 준비돼 있는지 설명하세요.\n"
        "gaps(현재 부족한 점): 아래를 찾으세요.\n"
        "1) 중복 과잉 — 오직 실손처럼 금액이 합산되지 않는 보장(비례보상)을 두 곳 이상 들어 "
        "실제로는 하나만 보상되는 경우만 지적하세요(duplicate_indemnity_count 참고). "
        "정액 담보(진단비·후유장해·수술비·사망 등)는 여러 건이어도 각각 지급되므로 "
        "중복이나 과잉으로 지적하지 마세요.\n"
        "2) 부족 — 이 나이·생애단계에서 흔히 필요한데 확인되지 않은 담보, "
        "또는 금액이 낮아 보이는 담보.\n"
        "gaps에는 왜 그런지 이유를 함께 적으세요.\n\n"
        "금액이 높거나 낮다는 의견, 과하거나 부족하다는 의견은 제시해도 됩니다. "
        "다만 공식 통계·기준이 있는 것처럼 단정하지 말고 "
        '"~해 보여요 / 확인해 보면 좋아요"처럼 여지를 두는 톤으로 쓰세요.\n\n'
        "overview(총평): 전체를 짧게 종합하세요. strengths·gaps에 이미 적은 개별 항목을 "
        "그대로 되풀이하지 말고, 전반적으로 무엇이 잘 갖춰졌고 무엇을 먼저 살펴보면 "
        "좋은지 큰 그림만 담으세요.\n\n"
        "절대 하지 말 것:\n"
        '- 특정 상품의 가입·해지·증액·감액을 지시하는 말투("~하세요").\n'
        "- 보험금 지급·보상·면책 여부 단정.\n"
        "- 제공되지 않은 개인 사실(가족력·소득·자녀 등)을 있다고 가정.\n"
        "amount_review_items에는 검토할 coverage evidence id만 고르세요. "
        "금액 문구는 서버가 조립합니다."
    )


def _user_prompt(
    demographics: InsuredDemographics,
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
    facts: PortfolioFacts,
    official_guidance: tuple[RetrievalHit, ...],
) -> str:
    categories = list(life_stage_check.held) + list(life_stage_check.missing)
    premium = summarize_premiums(list(facts.policies))
    payload = {
        "demographics": demographics.model_dump(mode="json"),
        "life_stage": life_stage_check.life_stage,
        "confirmed_categories": list(life_stage_check.held),
        "review_categories": list(life_stage_check.missing),
        "category_purposes": {
            category: coverage_purpose(category)
            for category in categories
            if coverage_purpose(category) is not None
        },
        "monthly_premium_total": premium.monthly_total,
        "duplicate_indemnity_count": count_duplicate_indemnity_coverages(facts.coverage_summary),
        "evidence": [item.model_dump(mode="json") for item in catalog.items],
        "official_guidance": [
            {
                "id": hit.chunk.id,
                "source_title": hit.chunk.source_title,
                "citation_label": hit.chunk.citation_label,
                "text": compact_prompt_text(hit.chunk.text, 700),
            }
            for hit in official_guidance
        ],
    }
    return dump_prompt_json(payload)
