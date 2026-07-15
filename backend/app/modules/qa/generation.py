"""LLM generation and filtering for conversational portfolio Q&A."""

from collections.abc import Iterator

from pydantic import BaseModel, Field

from app.integrations.openai.client import (
    JsonCompleter,
    TextStreamer,
    dump_prompt_json,
    stream_completion,
    structured_completer,
)
from app.modules.coverage.matching import (
    canonicalize_coverage_name,
    query_contains_canonical_name,
)
from app.modules.coverage.taxonomy import LifeStageCheck
from app.modules.evidence.catalog import (
    EvidenceCatalog,
    citation_from_evidence,
    filter_safe_unique_texts,
    is_safe_analysis_text,
    valid_evidence_ids,
)
from app.modules.policy.demographics import mask_demographic_identifiers
from app.modules.qa.claim_channels import claim_channel_block
from app.modules.qa.contracts import (
    AnswerSection,
    InsuredDemographics,
)
from app.modules.qa.schemas import (
    AnswerCitation,
    ConversationMessage,
    PortfolioQuestionResponse,
)

_MAX_HISTORY_MESSAGES = 12
_MAX_SUGGESTIONS = 3

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


def _markdown_section(title: str, content: str) -> str:
    return f"**{title}**\n\n{content.strip()}"


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
    suggestions: list[str] = Field(default_factory=list, max_length=_MAX_SUGGESTIONS)
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

    suggestions = _safe_question_suggestions(draft.suggestions)
    limitations = filter_safe_unique_texts(
        draft.limitations,
        is_safe=is_safe_analysis_text,
    )
    limitations.extend(standard_limitations)
    confirmed_content = "\n".join(
        f"- {catalog.by_id[evidence_id].fact}" for evidence_id in evidence_ids
    )
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
        answer="\n\n".join(
            _markdown_section(section.title, section.content) for section in sections
        ),
        sections=sections,
        citations=[
            citation_from_evidence(catalog.by_id[evidence_id]) for evidence_id in evidence_ids
        ],
        limitations=list(dict.fromkeys(limitations)),
        suggestions=suggestions,
        generation="llm",
    )


def _system_prompt() -> str:
    return """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 친절한 보험 상담사입니다.
새 상품 가입이나 해지를 권하는 판매원이 아닙니다.
지금 있는 보장을 근거로 궁금한 점에 답하는 상담사입니다.
친근한 존댓말(~해요체)로, 어려운 용어는 쉬운 말로 풀어서 답하세요.

[답변 표현]
- 사용자가 읽기 쉽게 Markdown 문법을 사용하세요.
- 중요한 보험명, 담보명, 금액, 판단 기준은 **굵게** 표시하세요.
- 여러 항목을 나열할 때는 bullet list를 사용하세요.
- 순서가 있는 절차는 numbered list를 사용하세요.
- 긴 문단 하나로 쓰지 말고, 짧은 문단과 목록으로 나누세요.

[confirmed_fact]
- 제공된 evidence로 확인되는 사실만 쓰세요. evidence에 없는 담보·금액·조건을 지어내지 마세요.
- evidence_ids는 제공된 id 중에서만 고르고, 실제로 근거로 쓴 id만 담으세요.

[guidance] (선택 항목)
- 지금 보장에서 함께 살펴보면 좋을 점을 일상적인 말로 편하게 제안하세요.
- 금액대를 언급해도 됩니다. 단 공식 기준이 아닌 일반 참고임을 밝히세요.
  (예: "정답은 아니지만 월 3만원 정도를 기준으로 보는 분들도 있어요")

[suggestions]
- 사용자가 그대로 누르거나 다시 물어볼 수 있는 질문 원문만 최대 3개 쓰세요.
- 모두 물음표로 끝내세요.
- "~해 보세요", "~확인해 주세요" 같은 행동 제안 문장은 쓰지 마세요.

[절대 하지 말 것 — 이걸 어기면 답변이 폐기됩니다]
- "지금 가입하세요 / 해지하세요 / 증액하세요" 같은 직접적인 가입·해지·증감 지시.
- 보상 가능 여부, 면책, 보험금 지급을 단정하는 말. 이는 약관 확인이 필요하니 판단하지 마세요.
- "공식 기준" 같은 표현으로 근거를 과장하는 말.
- 제공받지 않은 개인 사실(가족력·소득·부양가족 유무 등)을 지어내는 말.
- 이전 assistant 답변을 새로운 증거로 취급하는 것."""


def _safe_question_suggestions(items: list[str]) -> list[str]:
    accepted: list[str] = []
    for item in filter_safe_unique_texts(items, is_safe=is_safe_analysis_text):
        cleaned = " ".join(item.split())
        if not cleaned.endswith("?"):
            continue
        accepted.append(cleaned)
        if len(accepted) == _MAX_SUGGESTIONS:
            break
    return accepted


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
    serialized = dump_prompt_json(payload)
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
    sections = [f"[내 보험 근거]\n{dump_prompt_json(context)}"]

    recent = history[-_MAX_HISTORY_MESSAGES:]
    if recent:
        transcript = "\n".join(
            f"{'사용자' if message.role == 'user' else '상담사'}: {message.content}"
            for message in recent
        )
        sections.append(f"[이전 대화]\n{transcript}")

    sections.append(f"[지금 답할 질문]\n{question}")
    return mask_demographic_identifiers("\n\n".join(sections))


def _stream_system_prompt() -> str:
    return """당신은 사용자의 편에서 업로드된 보험을 함께 살펴보는 보험 상담사입니다.
특정 상품을 파는 판매원이 아니라, 지금 가진 보장을 기준으로 겹침·불필요·공백을 짚고
무엇을 고려하면 좋을지 구체적으로 도와주는 '내 편' 상담사입니다.
제공된 evidence만 근거로 삼아, 사용자에게 보여줄 답변 본문만 자연스럽게 쓰세요.
친근한 존댓말(~해요체)로, 어려운 용어는 쉬운 말로 풀어서 답하세요.

[답변 형식]
- 사용자에게 보여줄 본문은 Markdown으로 작성하세요.
- 중요한 보험명, 담보명, 금액, 판단 기준은 **굵게** 표시하세요.
- 여러 항목은 bullet list로 나누고, 절차는 numbered list를 사용하세요.
- 긴 plain text 문단 하나로 쓰지 말고, 결론과 주의할 점을 짧게 나누세요.
- Mermaid나 HTML은 사용하지 마세요.

[대화 맥락]
- [이전 대화]는 맥락 참고용입니다. 항상 마지막 [지금 답할 질문]에 답하세요.
- 이전에 이미 말한 내용은 기억하고, 같은 것을 다시 묻지 마세요.

[되묻기]
- 기본은 되묻지 않고 바로 답하는 것입니다. evidence에 있는 내용은 절대 되묻지 마세요.
- 특히 사용자의 가입 보험·담보·보장금액·상품명은 [내 보험 근거]에 이미 있으니,
  "어떤 보장을 받고 있는지" "무슨 보험이 있는지"를 사용자에게 묻지 말고 직접 찾아 답하세요.
- 되묻기는 오직 evidence에도 이전 대화에도 없고 사용자만 아는 사고·상황 사실이
  판단에 꼭 필요할 때만 씁니다(예: 어떤 사고인지, 어디를 다쳤는지, 언제 진단받았는지).
- 되물을 때만 첫 줄에 정확히 `CLARIFY`만 쓰고 다음 줄에 꼭 필요한 되물음 한 가지만 쓰세요.

[제안 — 회피하지 말고 구체적으로]
- "가입하면 좋을 보험·보장이 있어?"를 물으면 "상황마다 다르다/전문가와 상담"으로 미루지 말고,
  review_categories(생애단계 대비 확인되지 않은 보장)를 활용해 "이런 보장은 지금 증권에서
  확인되지 않으니 필요하면 고려해볼 만해요"처럼 구체적으로 알려주세요.
- "줄일 담보 있어?"를 물으면 evidence에서 여러 증권에 겹치는 담보(특히 실손·비례보상형은
  중복 가입해도 더 받지 못함)를 짚어 "이건 정리를 고려해볼 만해요"처럼 제안하세요.
- 이건 지금 가진 정보 기반의 참고 제안입니다. 특정 상품·보험사를 팔거나 손해 공포로
  압박하지 말고, 정확한 조건과 최종 결정은 약관·보험사에서 확인하도록 함께 안내하세요.

[보상·청구 질문 — 회피하지 말 것]
- "이거 보상돼? 어떻게 받아?"를 물으면 거절부터 하지 말고, 일반적으로 어떤 담보가 그 상황을
  처리하는지 근거 기반으로 설명하세요(예: 차량 파손은 자동차보험 대물·자차).
- 단, 실제 보상 여부·과실 비율·지급액은 단정하지 말고 "정확한 건 약관과 보험사 확인이
  필요해요"라고 함께 밝히세요.

[근거]
- evidence에 없는 담보·금액·조건을 지어내지 마세요.
- 사용자가 evidence에 없는 보험·보장을 물으면 "확인하기 어렵다"가 아니라,
  "지금 업로드된 증권에는 그 보장이 없어요"처럼 가입되어 있지 않다고 분명히 알려주세요.
- 금액대를 언급해도 됩니다. 단 공식 기준이 아닌 일반 참고임을 밝히세요.

[자동차보험 vs 운전자보험 — 반드시 구분]
- 차량 사고 자체(내 차·상대 차량 파손, 대물·대인, 접촉·추돌·주차 중 파손)의 보상·청구는
  오직 **자동차보험**이 담당합니다. evidence의 `auto:` 항목이 자동차보험입니다.
- **운전자보험**(보험분류 '손해보험', 상품태그 '운전자보험'인 상품)은 운전 중 사고로 생기는
  벌금·변호사선임비·형사합의금 등 '운전자 본인'을 돕는 보험이라, 차량 손해나 상대방
  보상(대물·대인)은 다루지 않습니다. 차량 사고 청구처로 운전자보험을 안내하지 마세요.
- `auto:` 항목이 없으면: "지금 업로드된 증권에는 자동차보험이 없어서 차량 사고 보상·청구는
  확인이 어려워요"라고 알려주세요. 운전자보험 등 다른 보험을 사고 청구처로 안내하지 마세요.

[하지 말 것]
- 특정 상품·보험사를 팔거나, 손해 공포로 가입을 압박하는 말.
- 보상 여부·과실·지급액을 단정하는 말("무조건 됩니다/안 됩니다"). 약관·보험사 확인이 필요합니다.
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
            cited.append(citation_from_evidence(item))
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
