"""LLM generation and filtering for conversational portfolio Q&A."""

import json

from pydantic import BaseModel, Field

from app.schemas.consultation import (
    AnswerSection,
    ConsultationEvidence,
    InsuredDemographics,
)
from app.schemas.qa import (
    AnswerCitation,
    ConversationMessage,
    PortfolioQuestionResponse,
)
from app.services.coverage_taxonomy import LifeStageCheck
from app.services.demographics import mask_demographic_identifiers
from app.services.llm import JsonCompleter, structured_completer
from app.services.portfolio_consultation import (
    EvidenceCatalog,
    is_safe_confirmed_fact,
    is_safe_general_guidance,
    valid_evidence_ids,
)

_MAX_HISTORY_MESSAGES = 12


class _LlmQaDraft(BaseModel):
    confirmed_fact: str = Field(min_length=1, max_length=700)
    guidance: str | None = Field(default=None, max_length=700)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    suggestions: list[str] = Field(default_factory=list, max_length=4)
    limitations: list[str] = Field(default_factory=list, max_length=4)


def generate_consultation_answer(
    *,
    fallback: PortfolioQuestionResponse,
    question: str,
    demographics: InsuredDemographics,
    history: list[ConversationMessage],
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
    standard_limitations: list[str],
    complete: JsonCompleter | None,
) -> PortfolioQuestionResponse:
    try:
        raw = (complete or structured_completer(_LlmQaDraft))(
            _system_prompt(),
            _user_prompt(question, demographics, history, life_stage_check, catalog),
        )
        draft = _LlmQaDraft.model_validate(raw)
    except Exception:
        return fallback

    evidence_ids = valid_evidence_ids(draft.evidence_ids, catalog)
    if evidence_ids is None or not is_safe_confirmed_fact(draft.confirmed_fact):
        return fallback
    if draft.guidance and not is_safe_general_guidance(draft.guidance):
        return fallback

    suggestions = [
        item.strip() for item in draft.suggestions if is_safe_general_guidance(item.strip())
    ]
    limitations = [
        item.strip() for item in draft.limitations if is_safe_general_guidance(item.strip())
    ]
    limitations.extend(standard_limitations)
    confirmed_content = " · ".join(catalog.by_id[evidence_id].fact for evidence_id in evidence_ids)
    sections = [
        AnswerSection(
            title="증권에서 확인된 사실",
            content=confirmed_content,
            basis="confirmed_fact",
        )
    ]
    if draft.guidance:
        sections.append(
            AnswerSection(
                title="함께 살펴볼 제안",
                content=draft.guidance.strip(),
                basis="general_guidance",
            )
        )
    return PortfolioQuestionResponse(
        status="answered",
        answer="\n\n".join(f"{section.title}\n{section.content}" for section in sections),
        sections=sections,
        citations=[_citation(catalog.by_id[evidence_id]) for evidence_id in evidence_ids],
        limitations=list(dict.fromkeys(limitations)),
        suggestions=list(dict.fromkeys(suggestions)),
        generation="llm",
    )


def _system_prompt() -> str:
    return """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 친절한 보험 상담사입니다.
새 상품 가입을 권하지 말고, 지금 있는 보장을 근거로 궁금한 점에 답하세요.
confirmed_fact에는 제공된 evidence로 확인되는 사실만 쓰고 숫자는 쓰지 마세요.
모든 evidence_ids는 제공된 id 중에서만 고르세요.
guidance의 금액 범위는 공식 기준이 아닌 일반 가이드임을 밝히세요.
보상 가능 여부, 면책, 보험금 지급 조건은 판단하지 마세요.
제공받지 않은 개인 사실을 가정하지 마세요.
이전 assistant 답변을 새로운 증거로 취급하지 마세요."""


def _user_prompt(
    question: str,
    demographics: InsuredDemographics,
    history: list[ConversationMessage],
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
) -> str:
    payload = {
        "question": question,
        "history": [
            message.model_dump(mode="json") for message in history[-_MAX_HISTORY_MESSAGES:]
        ],
        "demographics": demographics.model_dump(mode="json"),
        "life_stage": life_stage_check.life_stage,
        "confirmed_categories": list(life_stage_check.held),
        "review_categories": list(life_stage_check.missing),
        "evidence": [item.model_dump(mode="json") for item in catalog.items],
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return mask_demographic_identifiers(serialized)


def _citation(item: ConsultationEvidence) -> AnswerCitation:
    return AnswerCitation(
        evidence_id=item.id,
        policy_id=item.policy_id,
        insurer=item.insurer,
        product_name=item.product_name,
        coverage_name=item.coverage_name,
    )
