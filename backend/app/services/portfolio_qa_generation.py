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


def _grounding_context(
    demographics: InsuredDemographics,
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
) -> dict[str, object]:
    """The shared grounding payload both Q&A prompts feed the model."""

    return {
        "demographics": demographics.model_dump(mode="json"),
        "life_stage": life_stage_check.life_stage,
        "confirmed_categories": list(life_stage_check.held),
        "review_categories": list(life_stage_check.missing),
        "evidence": [item.model_dump(mode="json") for item in catalog.items],
    }


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
        **_grounding_context(demographics, life_stage_check, catalog),
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return mask_demographic_identifiers(serialized)


def _stream_user_prompt(
    question: str,
    demographics: InsuredDemographics,
    history: list[ConversationMessage],
    life_stage_check: LifeStageCheck,
    catalog: EvidenceCatalog,
) -> str:
    """Grounding context, then the prior conversation, then the current question.

    Ordering the current question last (and labelling it) keeps the model from
    drifting back to an earlier turn — it answers what was just asked while still
    using the transcript for context.
    """

    context = _grounding_context(demographics, life_stage_check, catalog)
    sections = [f"[내 보험 근거]\n{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"]

    recent = history[-_MAX_HISTORY_MESSAGES:]
    if recent:
        transcript = "\n".join(
            f"{'사용자' if message.role == 'user' else '상담사'}: {message.content}"
            for message in recent
        )
        sections.append(f"[이전 대화]\n{transcript}")

    sections.append(f"[지금 답할 질문]\n{question}")
    return mask_demographic_identifiers("\n\n".join(sections))


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

[대화 맥락]
- [이전 대화]는 맥락 참고용입니다. 항상 마지막 [지금 답할 질문]에 답하세요.
- 이전에 이미 말한 내용은 기억하고, 같은 것을 다시 묻지 마세요.

[되묻기]
- 기본은 되묻지 않고 바로 답하는 것입니다. evidence에 있는 내용은 절대 되묻지 마세요.
- 특히 사용자의 가입 보험·담보·보장금액·상품명은 [내 보험 근거]에 이미 있으니,
  "어떤 보장을 받고 있는지" "무슨 보험이 있는지"를 사용자에게 묻지 말고 직접 찾아 답하세요.
  ("확인해보셨나요?" "어떤 보험인지 말씀해 주세요" 같은 되물음 금지.)
- 되묻기는 오직 evidence에도 이전 대화에도 없고 사용자만 아는 사고·상황 사실이
  판단에 꼭 필요할 때만 씁니다(예: 어떤 사고인지, 어디를 다쳤는지, 언제 진단받았는지).
- 되물을 때만 첫 줄에 정확히 `CLARIFY`만 쓰고 다음 줄에 꼭 필요한 되물음 한 가지만 쓰세요.
  담보·금액·추측성 답변은 섞지 마세요.

[근거]
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


_CLARIFY_TOKEN = "CLARIFY"


_CLARIFY_SEPARATORS = " \t\r\n:：-"


class _ClarifyHeader:
    """Strip a leading `CLARIFY` control token from a token stream.

    Answers stream with no delay — the first character that can't extend
    "CLARIFY" resolves the turn as an answer. Only when the stream actually
    begins with the token do we buffer, then drop the token plus any trailing
    separator (newline, space, colon, dash) however the model wrote it —
    `CLARIFY\\n질문`, `CLARIFY 질문`, `CLARIFY: 질문` all yield just `질문`.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._decided = False
        self._trimming = False  # after the token, drop leading separators
        self.is_clarifying = False

    @property
    def status(self) -> str:
        return "clarify" if self.is_clarifying else "answered"

    def _trim_leading(self, text: str) -> str:
        if not self._trimming:
            return text
        cleaned = text.lstrip(_CLARIFY_SEPARATORS)
        if cleaned:
            self._trimming = False
        return cleaned

    def feed(self, delta: str) -> str | None:
        """Return display text for this delta, or None while still undecided."""

        if self._decided:
            return self._trim_leading(delta)

        self._buffer += delta
        probe = self._buffer.lstrip().upper()
        if probe.startswith(_CLARIFY_TOKEN):
            self.is_clarifying = True
            self._decided = True
            self._trimming = True
            remainder = self._buffer.lstrip()[len(_CLARIFY_TOKEN) :]
            self._buffer = ""
            return self._trim_leading(remainder)
        if probe == "" or _CLARIFY_TOKEN.startswith(probe):
            return None  # still could become the CLARIFY token — keep buffering
        self._decided = True
        body, self._buffer = self._buffer, ""
        return body

    def flush(self) -> str:
        if self._decided:
            return ""
        self._decided = True
        body, self._buffer = self._buffer, ""
        # Undecided leftover is a prefix of "CLARIFY" (e.g. "CLAR") or the bare
        # token with no question. A bare token means an empty clarify turn.
        if body.strip().upper() == _CLARIFY_TOKEN:
            self.is_clarifying = True
            return ""
        return body


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
    user = _stream_user_prompt(question, demographics, history, life_stage_check, catalog)

    parts: list[str] = []
    header = _ClarifyHeader()
    started = False
    interrupted = False

    def emit(text: str | None) -> Iterator[QaStreamEvent]:
        # Meta is deferred until the first visible token, so a header-only stream
        # (empty body) never announces a turn it can't deliver.
        nonlocal started
        if not text:
            return
        if not started:
            yield {"type": "meta", "status": header.status, "generation": "llm"}
            started = True
        parts.append(text)
        yield {"type": "delta", "text": text}

    try:
        for delta in streamer(system, user):
            if not delta:
                continue
            yield from emit(header.feed(delta))
    except Exception:
        interrupted = True

    yield from emit(header.flush())

    full = "".join(parts).strip()
    if not started or not full:
        yield from _fallback_stream(fallback)
        return

    end_limitations: list[str] = []
    if interrupted:
        # Mid-stream failure after partial text: the shown answer may be cut off.
        end_limitations.append("답변이 도중에 끊겼을 수 있어요. 다시 질문해 주세요.")

    if header.is_clarifying:
        yield {
            "type": "end",
            "status": "clarify",
            "generation": "llm",
            "citations": [],
            "limitations": end_limitations,
            "suggestions": [],
            "claim_channels": None,
        }
        return

    end_limitations.extend(limitations)
    end_limitations = list(dict.fromkeys(end_limitations))

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
