"""LLM generation and filtering for counselor-style portfolio analysis."""

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import (
    AnalysisContextAnswer,
    AnalysisContextKind,
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
from app.services.rag.official.models import RetrievalHit

# Strengths cite held coverages; gaps may also cite existing coverages/실손 to
# flag over-insurance, not only missing (gap:) categories.
_STRENGTH_PREFIXES = ("coverage:", "indemnity:")
_GAP_PREFIXES = ("gap:", "indemnity:", "excluded:")
_AUXILIARY_PREFIXES = ("official:",)


class _LlmInsight(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    detail: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)


class _LlmCounselorDraft(BaseModel):
    overview: str = Field(default="", max_length=600)
    strengths: list[_LlmInsight] = Field(default_factory=list, max_length=8)
    gaps: list[_LlmInsight] = Field(default_factory=list, max_length=8)
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
    personal_context: tuple[AnalysisContextAnswer, ...] = (),
) -> tuple[CounselorAnalysis, GenerationMode]:
    if not facts.policies:
        return fallback, "fallback"

    try:
        raw = (complete or structured_completer(_LlmCounselorDraft))(
            _system_prompt(),
            _user_prompt(
                demographics,
                life_stage_check,
                catalog,
                facts,
                official_guidance,
                personal_context,
            ),
        )
        draft = _LlmCounselorDraft.model_validate(raw)
    except Exception:
        return fallback, "fallback"

    strengths = _filter_insights(
        draft.strengths,
        catalog,
        allowed_prefixes=_STRENGTH_PREFIXES,
        section="strength",
    )
    gaps = _filter_insights(
        draft.gaps,
        catalog,
        allowed_prefixes=_GAP_PREFIXES,
        section="gap",
    )
    next_questions = filter_safe_unique_texts(
        draft.next_questions,
        is_safe=is_safe_analysis_text,
    )
    next_questions = _remove_answered_questions(next_questions, personal_context)
    next_steps = filter_safe_unique_texts(
        draft.next_steps,
        is_safe=is_safe_analysis_text,
    )
    accepted_count = sum(len(items) for items in (strengths, gaps, next_questions, next_steps))
    if accepted_count == 0:
        return fallback, "fallback"

    overview = _complete_overview(
        _safe_overview(draft.overview) or fallback.overview,
        facts,
        life_stage_check,
    )
    fallback_questions = _remove_answered_questions(
        fallback.next_questions,
        personal_context,
    )

    return (
        CounselorAnalysis(
            overview=overview,
            strengths=strengths or fallback.strengths,
            gaps=gaps or fallback.gaps,
            amount_review_items=[],
            next_questions=next_questions or fallback_questions,
            next_steps=next_steps or fallback.next_steps,
        ),
        "llm",
    )


def _filter_insights(
    drafts: list[_LlmInsight],
    catalog: EvidenceCatalog,
    *,
    allowed_prefixes: tuple[str, ...],
    section: Literal["strength", "gap"],
) -> list[CounselorInsight]:
    insights: list[CounselorInsight] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    seen_evidence: set[tuple[str, ...]] = set()
    for draft in drafts:
        evidence_ids = valid_evidence_ids(draft.evidence_ids, catalog)
        if evidence_ids is None:
            continue
        primary_evidence_ids = _primary_evidence_ids(evidence_ids, allowed_prefixes)
        if primary_evidence_ids is None:
            continue
        if primary_evidence_ids in seen_evidence:
            continue
        if any(
            not evidence_id.startswith(allowed_prefixes + _AUXILIARY_PREFIXES)
            for evidence_id in evidence_ids
        ):
            continue
        title = draft.title.strip()
        detail = draft.detail.strip()
        has_official_evidence = any(
            evidence_id.startswith(_AUXILIARY_PREFIXES) for evidence_id in evidence_ids
        )
        if not is_safe_analysis_text(title, allow_official_claims=has_official_evidence):
            title = _fallback_insight_title(primary_evidence_ids, catalog, section=section)
        if not is_safe_analysis_text(detail, allow_official_claims=has_official_evidence):
            detail = _fallback_insight_detail(primary_evidence_ids, catalog, section=section)
        repaired = _LlmInsight(title=title, detail=detail, evidence_ids=list(evidence_ids))
        if not _insight_matches_evidence(repaired, primary_evidence_ids, catalog):
            continue
        key = (title, detail, evidence_ids)
        if key in seen:
            continue
        seen.add(key)
        seen_evidence.add(primary_evidence_ids)
        insights.append(
            CounselorInsight(
                title=title,
                detail=detail,
                evidence_ids=list(evidence_ids),
            )
        )
    return insights


def _primary_evidence_ids(
    evidence_ids: tuple[str, ...], allowed_prefixes: tuple[str, ...]
) -> tuple[str, ...] | None:
    primary = tuple(
        evidence_id for evidence_id in evidence_ids if evidence_id.startswith(allowed_prefixes)
    )
    return primary or None


def _fallback_insight_title(
    evidence_ids: tuple[str, ...],
    catalog: EvidenceCatalog,
    *,
    section: Literal["strength", "gap"],
) -> str:
    evidence = catalog.by_id[evidence_ids[0]]
    coverage_name = evidence.coverage_name or "확인 항목"
    if section == "strength":
        return f"{coverage_name} 담보가 확인돼요"
    return f"{coverage_name} 항목을 확인해 보세요"


def _fallback_insight_detail(
    evidence_ids: tuple[str, ...],
    catalog: EvidenceCatalog,
    *,
    section: Literal["strength", "gap"],
) -> str:
    evidence = catalog.by_id[evidence_ids[0]]
    coverage_name = evidence.coverage_name
    category = classify_coverage(coverage_name or "")
    purpose = coverage_purpose(category) if category else None
    if evidence.id.startswith("gap:"):
        unconfirmed = "현재 업로드된 비자동차 증권에서는 이 성격의 보장이 확인되지 않았어요."
        return f"{purpose} {unconfirmed}" if purpose else unconfirmed
    if evidence.id.startswith("excluded:"):
        return evidence.fact
    confirmed = "현재 증권에서 이 담보의 가입 사실을 확인했어요."
    return f"{purpose} {confirmed}" if purpose else confirmed


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


def _remove_answered_questions(
    questions: list[str], personal_context: tuple[AnalysisContextAnswer, ...]
) -> list[str]:
    answered_questions = {_normalized_question(item.question) for item in personal_context}
    answered_context = _answered_context_kinds(personal_context)
    return [
        question
        for question in questions
        if _normalized_question(question) not in answered_questions
        and not (_context_kind(question) and _context_kind(question) in answered_context)
    ]


def _safe_overview(overview: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+|\n+", overview.strip())
    return " ".join(
        sentence.strip()
        for sentence in sentences
        if sentence.strip() and is_safe_analysis_text(sentence)
    )


def _complete_overview(
    overview: str,
    facts: PortfolioFacts,
    _life_stage_check: LifeStageCheck,
) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", overview.strip())
    has_portfolio_scope = any(
        phrase in overview
        for phrase in ("두 건", "두 보험", "여러 보험", "전체", "포트폴리오", "합쳐", "흩어진")
    )
    if len(facts.policies) > 1 and not has_portfolio_scope and len(sentences) < 5:
        sentences.insert(0, "보험사별로 흩어진 같은 성격의 담보는 하나로 합쳐 살펴봤어요.")
    return " ".join(sentences)


def _answered_context_kinds(
    personal_context: tuple[AnalysisContextAnswer, ...],
) -> set[AnalysisContextKind]:
    return {kind for item in personal_context if (kind := _context_kind(item.question)) is not None}


def _context_kind(text: str) -> AnalysisContextKind | None:
    if "소득" in text:
        return "소득"
    if "생활비" in text:
        return "치료·회복 기간 생활비"
    if "부양" in text or "가족" in text:
        return "부양 책임"
    if "예산" in text or "보험료" in text or "납입" in text:
        return "가용 예산"
    return None


def _normalized_question(text: str) -> str:
    return "".join(character for character in text.casefold() if character.isalnum())


def _system_prompt() -> str:
    return """# 역할
당신은 사용자가 이미 가입한 보험들을 정밀하게 분석하는 보험 분석가입니다.
보험 판매원이나 가입 권유자가 아니라, 업로드된 증권에서 확인되는 사실을
전문적으로 분석해 쉬운 말로 설명합니다.

# 제품 목적
- 여러 보험사와 여러 증권에 흩어진 보장을 하나의 포트폴리오로 합쳐 분석합니다.
- 사용자가 증권을 따로 읽을 때 놓치기 쉬운 보장 구성, 중복 가능성, 확인되지 않은 축을 찾습니다.
- 보험 용어를 반복하는 대신, 그 사실이 치료비·생활비·소득 변화와 어떤 관련이 있는지
  쉬운 말로 구체적으로 설명합니다.
- 개별 보험을 차례로 요약하지 말고 모든 증권을 함께 봤을 때 새롭게 알 수 있는 사실을 우선합니다.

# 목표
업로드된 비자동차 보험 포트폴리오를 분석해 structured schema의 다음 필드를 생성합니다.
- overview: 전체 상태 요약
- strengths: 현재 확인된 보장의 강점
- gaps: 확인되지 않았거나 점검이 필요한 항목
- next_questions: 사용자가 답하면 분석이 좋아지는 개인 맥락 질문
- next_steps: 사용자가 다음에 확인할 행동

# 사용할 수 있는 근거
다음 입력만 사실로 사용합니다.
- demographics
- life_stage
- confirmed_categories
- review_categories
- category_purposes
- monthly_premium_total
- duplicate_indemnity_count
- evidence
- official_guidance
- personal_context

없는 담보, 없는 금액, 없는 가족력, 없는 소득, 없는 자녀 정보는 만들지 않습니다.

# personal_context 사용 규칙
- personal_context는 사용자가 이번 분석을 위해 직접 답한 정보입니다.
- 증권에서 확인된 사실과 구분하고, 사용자가 말한 범위 안에서 overview와 점검 순서에 반영합니다.
- 답변하지 않은 소득, 생활비, 부양 책임, 예산을 추정하지 않습니다.
- 이미 답한 내용을 next_questions에서 다시 묻지 않습니다.

# official_guidance 사용 규칙
- official_guidance와 official: evidence는 공식자료에서 검색된 보조 근거입니다.
- 지급사유, 면책, 감액, 보상하지 않는 사항, 제도 설명, 통계가 들어 있으면
  그 근거 범위 안에서 설명할 수 있습니다.
- official_guidance에 없는 공식 기준·통계·수치를 새로 만들지 마세요.
- official_guidance나 official: evidence만으로 사용자가 가진 담보의 존재, 가입금액, 중복 여부,
  개인별 적정 가입금액, 실제 보험금 지급 가능성을 만들거나 단정하지 않습니다.

# evidence 사용 규칙
1. 모든 strengths/gaps 항목은 입력에 실제 존재하는 evidence id만 사용합니다.
2. strengths는 현재 확인된 보장만 다룹니다.
   사용할 수 있는 evidence id는 coverage:, indemnity: 입니다.
3. gaps는 다음 중 하나만 다룹니다.
   - 확인되지 않은 생애단계 점검 항목: gap:
   - 실손 등 비례보상 중복 가능성: indemnity:
   - 금액/지급유형 불명으로 분석에서 제외된 담보: excluded:
4. 인용한 evidence와 다른 주제로 말하지 않습니다.
5. 여러 evidence를 묶을 때는 같은 주제를 뒷받침하는 경우에만 묶습니다.
6. official: evidence는 coverage:, indemnity:, gap:, excluded: evidence와 함께 쓰는
   보조 근거입니다. official: evidence만 단독으로 strengths/gaps를 만들지 않습니다.
7. 지급사유, 면책, 감액, 보상하지 않는 사항, 제도 설명, 통계를 설명하는
   strengths/gaps 항목은 반드시 관련 official: evidence id도 함께 인용합니다.
   예: ["indemnity:1", "official:1"].
8. 공식자료 내용이 항목 설명에 직접 쓰이지 않으면 official: evidence를 억지로 붙이지 않습니다.

# 작업 순서
1. evidence를 먼저 읽고 현재 확인된 보장과 금액을 파악합니다.
2. confirmed_categories와 category_purposes를 참고해 strengths를 고릅니다.
3. review_categories와 gap evidence를 참고해 확인되지 않은 항목을 고릅니다.
4. duplicate_indemnity_count가 있을 때만 실손형 중복 가능성을 gaps에 씁니다.
5. official: evidence를 읽고, 지급사유·면책·감액·보상하지 않는 사항·제도 설명을
   직접 언급하는 항목에는 policy evidence와 official evidence를 함께 붙입니다.
6. overview는 3~5문장으로 작성합니다.
   전체 증권을 합쳐 봤을 때의 큰 그림, 함께 묶여 확인되는 보장 축,
   따로 읽을 때 놓치기 쉬운 사실을 자연스럽게 연결합니다.
   strengths/gaps 제목을 그대로 나열하는 방식은 피합니다.
7. next_questions는 개인 맥락을 묻고, next_steps는 가입 권유가 아닌 확인 행동을 제안합니다.

# 표현 원칙
- 너무 방어적으로 빈말만 하지 말고, 확인된 근거 안에서는 유용한 분석을 말합니다.
- 단정 대신 여지를 둡니다. 예: "기반은 확인돼요", "점검해볼 만해요", "비교해보면 좋아요".
- 공식자료, 증권, 계산 근거가 있을 때는 그 범위 안에서
  기준·통계·제도·지급 구조를 설명할 수 있습니다.
- 근거가 없을 때만 "충분합니다", "부족합니다", "필요합니다"처럼
  공식 기준이 있는 듯한 확정 표현을 피합니다.
- "추가 가입", "증액", "해지", "감액"을 권하지 않습니다.
- "추가 보장이 필요합니다", "보장을 더 준비해야 합니다"처럼 가입 필요로 읽히는 표현을 쓰지 않습니다.
- "추가적인 보장", "추가 보장 항목", "보장 항목을 더 준비" 같은 표현도 쓰지 않습니다.
  확인되지 않은 항목은 "다른 증권에 있는지 확인", "개인 맥락과 함께 점검"으로 표현합니다.
- 사용자의 실제 보험금 지급 가능성, 보상 가능, 면책 여부는 단정하지 않습니다.

# strengths 작성 규칙
- detail은 2문장으로 씁니다.
  첫 문장은 증권에서 확인된 담보와 가입 사실을 말하고,
  두 번째 문장은 그 보장이 어떤 비용·생활 변화에 대비하는지 설명합니다.
- 금액을 언급할 수 있지만 개인별 적정성은 확정하지 않습니다.
- 각 strength의 detail은 서로 다른 문장 구조로 씁니다.
  "대응하는 성격이에요" 같은 같은 어미와 표현을 반복하지 않습니다.
- category_purposes 문장을 그대로 복사하지 말고, evidence의 담보명·금액과 연결해
  사용자가 이해하기 쉬운 두 문장으로 다시 씁니다.
- 실손형 담보는 "실제 지출 치료비를 무조건 돌려받는다"가 아니라
  "치료비 부담을 약관상 조건에 따라 보전하는 성격"처럼 구조로 설명합니다.
- 실손형 담보를 설명할 때 "돌려받아", "보장받을 수 있습니다", "보상받을 수 있습니다"처럼
  사용자의 실제 지급 가능성을 확정하는 표현은 쓰지 않습니다.
- 좋은 예: "암진단비 3천만원은 진단 초기 목돈 대비의 기반으로 볼 수 있어요."
- 실손형 좋은 예: "실손의료비는 치료비 부담을 약관상 조건, 한도,
  자기부담금에 따라 보전하는 성격이에요."

# overview 작성 규칙
- 너무 짧은 한 문장으로 끝내지 않습니다.
- 첫 문장은 여러 증권을 하나로 합쳐 본 결과를 말합니다.
- 두 번째 문장은 전체 포트폴리오에서 확인된 큰 보장 축과 의미를 설명합니다.
- 세 번째 문장은 따로 읽을 때 놓치기 쉬운 확인 항목을 설명합니다.
- 필요하면 네 번째나 다섯 번째 문장에서 추가로 알면 좋은 맥락을 말합니다.
- 마지막 문장을 쓸 때도 추가 가입 필요가 아니라,
  다른 증권 확인이나 개인 맥락 확인으로 마무리합니다.
- strengths/gaps의 제목과 detail을 그대로 다시 나열하거나 복사하지 않습니다.

# gaps 작성 규칙
- detail은 2문장으로 씁니다.
  첫 문장은 업로드한 증권에서 확인되지 않았다는 사실을 말하고,
  두 번째 문장은 어떤 비용·생활 변화와 관련돼 있어 확인할 가치가 있는지 설명합니다.
- 확인되지 않은 항목을 실제 보장 공백이나 부족으로 확정하지 않습니다.
- 확인 이유를 설명하되 공포를 유도하지 않습니다.
- 정액 담보는 여러 건이어도 중복 과잉으로 말하지 않습니다.
- 실손형/비례보상 담보만 중복 가능성으로 다룹니다.

# next_questions / next_steps 규칙
- next_questions는 분석에서 알고 싶은 점, 아직 올리지 않은 보험, 가족 생활비 책임처럼
  답이 분석의 설명 순서를 바꿀 수 있는 개인 맥락을 묻습니다.
- next_steps는 다른 증권 확인, 약관의 지급사유·면책·감액 조건 확인,
  최신 계약 상태 확인 같은 행동을 제안합니다.
- 특정 상품의 추가 가입을 고려하라고 말하지 않습니다.

# 출력 규칙
- structured schema에 맞춰 반환합니다.
- 근거가 부족한 항목은 만들지 않습니다."""


def _user_prompt(
    demographics: InsuredDemographics,
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
    facts: PortfolioFacts,
    official_guidance: tuple[RetrievalHit, ...],
    personal_context: tuple[AnalysisContextAnswer, ...],
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
                "evidence_id": f"official:{index}",
                "source_title": hit.chunk.source_title,
                "citation_label": hit.chunk.citation_label,
                "text": compact_prompt_text(hit.chunk.text, 700),
            }
            for index, hit in enumerate(official_guidance, start=1)
        ],
        "personal_context": [item.model_dump(mode="json") for item in personal_context],
    }
    return dump_prompt_json(payload)
