"""LLM generation and filtering for conversational portfolio Q&A."""

import json
from collections.abc import Iterator

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
from app.services.claim_channels import claim_channel_block
from app.services.coverage_name_matching import (
    canonicalize_coverage_name,
    query_contains_canonical_name,
)
from app.services.coverage_taxonomy import LifeStageCheck
from app.services.demographics import mask_demographic_identifiers
from app.services.llm import JsonCompleter, TextStreamer, stream_completion, structured_completer
from app.services.portfolio_consultation import (
    EvidenceCatalog,
    is_safe_analysis_text,
    valid_evidence_ids,
)

_MAX_HISTORY_MESSAGES = 12

# One event of the /qa/stream Server-Sent-Events protocol: meta → delta* → end.
QaStreamEvent = dict[str, object]

# When a conversational answer is about claiming/receiving a benefit, we attach
# the deterministic insurer claim channels so the user gets a real link to act on.
_CLAIM_INTENT_TERMS = (
    "청구",
    "보험금",
    "진단서",
    "청구서",
    "접수",
    "서류",
    "지급",
    "받으",
    "신청",
)


def _is_claim_related(question: str, answer: str) -> bool:
    haystack = f"{question}\n{answer}"
    return any(term in haystack for term in _CLAIM_INTENT_TERMS)


def _claim_channels_for_answer(
    question: str, answer: str, claim_targets: list[tuple[str, str, bool]]
) -> dict[str, object] | None:
    """Channels for the insurers whose coverage the answer actually names.

    The LLM's own answer decides which coverages matter; we resolve those to the
    policy insurers that can pay the claim, so the user gets the right link — not
    every uploaded insurer, and not a coverage the answer never mentioned.
    """

    haystack = f"{question}\n{answer}"
    insurers: list[str] = []
    has_indemnity = False
    for normalized_name, insurer, is_indemnity in claim_targets:
        if query_contains_canonical_name(haystack, normalized_name):
            insurers.append(insurer)
            has_indemnity = has_indemnity or is_indemnity
    insurers = list(dict.fromkeys(insurers))
    if not insurers:
        return None
    block = claim_channel_block(insurers, has_indemnity=has_indemnity)
    if not block.insurers and block.indemnity is None:
        return None
    return block.model_dump(mode="json")


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
    if evidence_ids is None or not is_safe_analysis_text(draft.confirmed_fact):
        return fallback

    # Degrade, don't discard: an unsafe optional guidance is dropped while the
    # evidence-grounded confirmed answer is still returned.
    guidance = draft.guidance.strip() if draft.guidance else ""
    if guidance and not is_safe_analysis_text(guidance):
        guidance = ""

    suggestions = [
        item.strip() for item in draft.suggestions if is_safe_analysis_text(item.strip())
    ]
    limitations = [
        item.strip() for item in draft.limitations if is_safe_analysis_text(item.strip())
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
    if guidance:
        sections.append(
            AnswerSection(
                title="함께 살펴볼 제안",
                content=guidance,
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
새 상품 가입이나 해지를 권하는 판매원이 아닙니다.
지금 있는 보장을 근거로 궁금한 점에 답하는 상담사입니다.
친근한 존댓말(~해요체)로, 어려운 용어는 쉬운 말로 풀어서 답하세요.

[confirmed_fact]
- 제공된 evidence로 확인되는 사실만 쓰세요. evidence에 없는 담보·금액·조건을 지어내지 마세요.
- evidence_ids는 제공된 id 중에서만 고르고, 실제로 근거로 쓴 id만 담으세요.

[guidance] (선택 항목)
- 지금 보장에서 함께 살펴보면 좋을 점을 일상적인 말로 편하게 제안하세요.
- 금액대를 언급해도 됩니다. 단 공식 기준이 아닌 일반 참고임을 밝히세요.
  (예: "정답은 아니지만 월 3만원 정도를 기준으로 보는 분들도 있어요")

[절대 하지 말 것 — 이걸 어기면 답변이 폐기됩니다]
- "지금 가입하세요 / 해지하세요 / 증액하세요" 같은 직접적인 가입·해지·증감 지시.
- 보상 가능 여부, 면책, 보험금 지급을 단정하는 말. 이는 약관 확인이 필요하니 판단하지 마세요.
- "공식 기준" 같은 표현으로 근거를 과장하는 말.
- 제공받지 않은 개인 사실(가족력·소득·부양가족 유무 등)을 지어내는 말.
- 이전 assistant 답변을 새로운 증거로 취급하는 것."""


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


def _stream_system_prompt() -> str:
    return """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 친절한 보험 상담사입니다.
새 상품 가입이나 해지를 권하는 판매원이 아닙니다.
제공된 evidence만 근거로 삼아, 사용자에게 보여줄 답변 본문만 자연스럽게 쓰세요.
친근한 존댓말(~해요체)로, 어려운 용어는 쉬운 말로 풀어서 답하세요.

- evidence에 없는 담보·금액·조건을 지어내지 마세요.
  근거가 없으면 "지금 증권만으로는 확인하기 어려워요"라고 솔직하게 말하세요.
- 금액대를 언급해도 됩니다. 단 공식 기준이 아닌 일반 참고임을 밝히세요.
  (예: "정답은 아니지만 월 3만원 정도를 기준으로 보는 분들도 있어요")

[하지 말 것]
- "지금 가입하세요 / 해지하세요 / 증액하세요" 같은 직접적인 가입·해지·증감 지시.
- 보상 가능 여부·면책·보험금 지급을 단정하는 말(약관 확인이 필요합니다).
- "공식 기준" 같은 근거 과장, 제공받지 않은 개인 사실(가족력·소득 등) 지어내기.
- 이전 assistant 답변을 새로운 증거로 취급하기."""


def _relevant_citations(answer: str, catalog: EvidenceCatalog) -> list[AnswerCitation]:
    """Cite the catalog facts whose coverage the answer itself names.

    Matches the answer text only — not the question — so a citation reflects what
    the answer is actually grounded in, not merely a coverage the user asked about.
    """

    cited: list[AnswerCitation] = []
    seen: set[str] = set()
    for item in catalog.items:
        if item.coverage_name is None or item.id in seen:
            continue
        base_name = item.coverage_name.split("(")[0].strip() or item.coverage_name
        normalized = canonicalize_coverage_name(base_name).normalized_key
        if query_contains_canonical_name(answer, normalized):
            seen.add(item.id)
            cited.append(_citation(item))
    return cited


def _fallback_stream(fallback: PortfolioQuestionResponse) -> Iterator[QaStreamEvent]:
    yield {"type": "meta", "status": fallback.status, "generation": "fallback"}
    yield {"type": "delta", "text": fallback.answer}
    yield {
        "type": "end",
        "status": fallback.status,
        "generation": "fallback",
        "citations": [citation.model_dump(mode="json") for citation in fallback.citations],
        "limitations": fallback.limitations,
        "suggestions": fallback.suggestions,
        "claim_channels": None,
    }


def stream_consultation_answer(
    *,
    question: str,
    demographics: InsuredDemographics,
    history: list[ConversationMessage],
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
    limitations: list[str],
    suggestions: list[str],
    fallback: PortfolioQuestionResponse,
    claim_targets: list[tuple[str, str, bool]] | None = None,
    stream: TextStreamer | None = None,
) -> Iterator[QaStreamEvent]:
    """Stream the LLM's own grounded prose; fall back if it never produces text."""

    streamer = stream or stream_completion
    system = _stream_system_prompt()
    user = _user_prompt(question, demographics, history, life_stage_check, catalog)

    parts: list[str] = []
    started = False
    interrupted = False
    try:
        for delta in streamer(system, user):
            if not delta:
                continue
            if not started:
                yield {"type": "meta", "status": "answered", "generation": "llm"}
                started = True
            parts.append(delta)
            yield {"type": "delta", "text": delta}
    except Exception:
        interrupted = True

    full = "".join(parts).strip()
    if not started or not full:
        yield from _fallback_stream(fallback)
        return

    end_limitations = list(dict.fromkeys(limitations))
    if interrupted:
        # Mid-stream failure after partial text: the shown answer may be cut off.
        end_limitations.insert(0, "답변이 도중에 끊겼을 수 있어요. 다시 질문해 주세요.")

    citations = _relevant_citations(full, catalog)
    channels_payload = None
    if _is_claim_related(question, full):
        channels_payload = _claim_channels_for_answer(question, full, claim_targets or [])
    yield {
        "type": "end",
        "status": "answered",
        "generation": "llm",
        "citations": [citation.model_dump(mode="json") for citation in citations],
        "limitations": end_limitations,
        "suggestions": list(dict.fromkeys(suggestions)),
        "claim_channels": channels_payload,
    }
