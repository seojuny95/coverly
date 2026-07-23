"""LLM overview copy for the portfolio summary screen."""

import logging
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.core.prompts import load_prompt
from app.integrations.openai.client import JsonCompleter, dump_prompt_json, structured_completer
from app.modules.portfolio.schemas import (
    EssentialCoverageItem,
    PortfolioCoverageSummary,
    PortfolioOverview,
)
from app.modules.portfolio.summary import duplicate_actual_loss_coverage_names

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).with_name("overview_prompt.md")


class SummaryOverviewUnavailableError(RuntimeError):
    """Raised when the required LLM overview cannot be generated safely."""


type _OverviewRole = Literal["confirmed", "review", "unconfirmed"]
type _OverviewText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=10, max_length=240)
]
type _OverviewTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=5, max_length=80)
]
type _FactId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class _OverviewParagraphSlot(BaseModel):
    slot_id: _FactId
    role: _OverviewRole
    fact_ids: list[_FactId] = Field(min_length=1)
    requires_limitation: bool = False


class _LlmParagraphDraft(BaseModel):
    slot_id: _FactId
    text: _OverviewText
    limitation: _OverviewText | None = None


class _LlmOverviewDraft(BaseModel):
    title: _OverviewTitle = Field(
        description="입력의 구체적인 보장 흐름을 담고 ~해요 형태로 끝나는 제목"
    )
    title_slot_id: _FactId
    paragraphs: list[_LlmParagraphDraft] = Field(
        min_length=1,
        max_length=3,
    )


def attach_summary_overview(
    summary: PortfolioCoverageSummary,
    complete: JsonCompleter | None = None,
) -> PortfolioCoverageSummary:
    """Attach LLM copy generated only from structured portfolio facts."""

    overview = generate_summary_overview(summary, complete)
    if overview is None:
        raise SummaryOverviewUnavailableError("Portfolio overview generation failed")
    return summary.model_copy(update={"overview": overview})


def generate_summary_overview(
    summary: PortfolioCoverageSummary,
    complete: JsonCompleter | None = None,
) -> PortfolioOverview | None:
    if not summary.essential_coverage_check.items:
        return None

    facts = _overview_prompt_facts(summary)
    completer = complete or structured_completer(_LlmOverviewDraft)
    try:
        raw = completer(_system_prompt(), _user_prompt(facts))
        draft = _LlmOverviewDraft.model_validate(raw)
    except Exception:
        logger.exception("portfolio_overview_generation_failed")
        return None

    if not _draft_uses_grounded_slots(draft, facts):
        try:
            raw = completer(_system_prompt(), _correction_user_prompt(facts, raw))
            draft = _LlmOverviewDraft.model_validate(raw)
        except Exception:
            logger.exception("portfolio_overview_correction_failed")
            return None
        if not _draft_uses_grounded_slots(draft, facts):
            logger.warning("portfolio_overview_grounding_failed")
            return None

    return PortfolioOverview(
        generation="llm",
        title=draft.title,
        paragraphs=_public_paragraphs(draft),
    )


def _overview_prompt_facts(summary: PortfolioCoverageSummary) -> dict[str, object]:
    """Expose structured facts without prewritten user-facing conclusions."""

    coverage_facts = _coverage_facts(summary.essential_coverage_check.items)
    duplicate_facts = _duplicate_actual_loss_facts(summary)
    facts = [*coverage_facts, *duplicate_facts]
    return {
        "facts": facts,
        "paragraph_slots": [
            slot.model_dump(mode="json") for slot in _overview_paragraph_slots(facts)
        ],
        "limitations": [
            "업로드한 자료에서 확인한 내용만 사용",
            "현재 자료에서 확인되지 않은 항목을 실제 미가입으로 단정하지 않음",
            "보험료와 보장의 충분성·적정성은 판단하지 않음",
        ],
    }


def _coverage_facts(items: list[EssentialCoverageItem]) -> list[dict[str, object]]:
    return [
        {
            "fact_id": f"core:{item.kind}",
            "role": _coverage_role(item),
            "kind": item.kind,
            "label": item.label,
            "observation": _coverage_observation(item),
            "explanation_basis": item.reference_basis,
            "matched_coverage_names": item.matched_coverage_names,
            "review_groups": [
                {
                    "label": group.label,
                    "tone": group.tone,
                    "coverage_names": group.coverage_names,
                }
                for group in item.coverage_groups
            ],
            "multiple_contracts": (
                item.kind == "medical_indemnity" and item.status == "needs_review"
            ),
        }
        for item in items
    ]


def _duplicate_actual_loss_facts(
    summary: PortfolioCoverageSummary,
) -> list[dict[str, object]]:
    duplicate_names = set(duplicate_actual_loss_coverage_names(summary))
    facts: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in summary.actual_loss_coverages:
        if item.coverage_name not in duplicate_names:
            continue
        key = (item.coverage_domain, item.normalized_name or item.coverage_name)
        if key in seen:
            continue
        seen.add(key)
        facts.append(
            {
                "fact_id": f"actual_loss_duplicate:{len(facts)}",
                "role": "review",
                "coverage_name": item.coverage_name,
                "coverage_domain": item.coverage_domain,
                "observation": "same_actual_loss_coverage_in_multiple_contracts",
                "same_name_in_multiple_contracts": True,
                "payout_or_duplicate_benefit_confirmed": False,
                "requires_terms_review": True,
            }
        )
    return facts


def _coverage_role(item: EssentialCoverageItem) -> _OverviewRole:
    if item.status == "not_found":
        return "unconfirmed"
    if item.status == "needs_review":
        return "review"
    return "confirmed"


def _coverage_observation(item: EssentialCoverageItem) -> str:
    if item.status == "not_found":
        return "not_confirmed_in_current_materials"
    if item.status == "needs_review":
        return "confirmed_but_needs_terms_review"
    return "confirmed_in_uploaded_documents"


def _overview_paragraph_slots(
    facts: list[dict[str, object]],
) -> list[_OverviewParagraphSlot]:
    slots: list[_OverviewParagraphSlot] = []
    for role in ("confirmed", "review", "unconfirmed"):
        fact_ids = [
            fact["fact_id"]
            for fact in facts
            if fact.get("role") == role and isinstance(fact.get("fact_id"), str)
        ]
        if fact_ids:
            slots.append(
                _OverviewParagraphSlot(
                    slot_id=f"{role}:summary",
                    role=role,
                    fact_ids=fact_ids,
                    requires_limitation=role == "unconfirmed",
                )
            )
    return slots


def _draft_uses_grounded_slots(
    draft: _LlmOverviewDraft,
    prompt_facts: dict[str, object],
) -> bool:
    slots_by_id = _slots_by_id(prompt_facts)
    if not slots_by_id or draft.title_slot_id not in slots_by_id:
        return False

    paragraph_slot_ids: list[str] = []
    for paragraph in draft.paragraphs:
        slot = slots_by_id.get(paragraph.slot_id)
        if slot is None:
            return False
        if slot.requires_limitation and paragraph.limitation is None:
            return False
        if not slot.requires_limitation and paragraph.limitation is not None:
            return False
        paragraph_slot_ids.append(paragraph.slot_id)

    return len(paragraph_slot_ids) == len(set(paragraph_slot_ids))


def _public_paragraphs(draft: _LlmOverviewDraft) -> list[str]:
    paragraphs: list[str] = []
    for paragraph in draft.paragraphs:
        if paragraph.limitation is not None:
            paragraphs.append(f"{paragraph.text} {paragraph.limitation}")
        else:
            paragraphs.append(paragraph.text)
    return paragraphs


def _slots_by_id(prompt_facts: dict[str, object]) -> dict[str, _OverviewParagraphSlot]:
    raw_slots = prompt_facts.get("paragraph_slots")
    if not isinstance(raw_slots, list):
        return {}

    slots: dict[str, _OverviewParagraphSlot] = {}
    for raw_slot in raw_slots:
        try:
            slot = _OverviewParagraphSlot.model_validate(raw_slot)
        except Exception:
            return {}
        slots[slot.slot_id] = slot
    return slots


def _system_prompt() -> str:
    return load_prompt(_PROMPT_PATH)


def _user_prompt(facts: dict[str, object]) -> str:
    return dump_prompt_json(
        {
            "task": "아래 확인 사실만으로 전체 보험 총평을 새로 작성하세요.",
            "facts": facts,
        }
    )


def _correction_user_prompt(
    facts: dict[str, object],
    previous_draft: dict[str, object],
) -> str:
    return dump_prompt_json(
        {
            "task": (
                "이전 총평은 문단 슬롯 배치가 입력 사실과 맞지 않았습니다. "
                "실제 입력 paragraph_slots의 slot_id만 중복 없이 사용해 다시 작성하세요. "
                "중요도가 낮은 슬롯은 생략해도 됩니다."
            ),
            "facts": facts,
            "previous_draft": previous_draft,
        }
    )
