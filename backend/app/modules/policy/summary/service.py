"""Public orchestration for extracting a display-ready policy summary."""

from collections.abc import Callable

from app.core.grounding import wording_grounded
from app.modules.policy.classification import classify_policy
from app.modules.policy.demographics import mask_demographic_identifiers
from app.modules.policy.models import PolicySummary
from app.modules.policy.summary.catalog import (
    get_insurer_aliases,
    get_insurer_candidates,
    get_insurer_contact_evidence,
    insurer_name_is_grounded,
    match_insurer_from_text,
)
from app.modules.policy.summary.llm import (
    LlmPolicySummary,
    _coerce_policy_summary,
    _LlmPolicySummaryExtraction,
    extract_policy_summary_with_llm,
)
from app.modules.policy.summary.local import extract_local_policy_summary

__all__ = [
    "LlmPolicySummary",
    "_LlmPolicySummaryExtraction",
    "_coerce_policy_summary",
    "extract_local_policy_summary",
    "extract_policy_summary",
    "extract_policy_summary_with_llm",
    "get_insurer_aliases",
    "get_insurer_candidates",
    "get_insurer_contact_evidence",
    "match_insurer_from_text",
]

_LLM_FILLABLE_FIELDS = [
    "보험사",
    "상품명",
    "증권번호",
    "계약자",
    "피보험자",
    "보험기간",
    "만기일",
    "납입기간",
    "보험료",
    "차량정보",
]
_LLM_TRIGGER_FIELDS = [
    field for field in _LLM_FILLABLE_FIELDS if field not in {"보험사", "납입기간", "차량정보"}
]
_GROUNDED_LLM_FIELDS = {"보험사", "증권번호", "계약자", "피보험자", "상품명"}


def extract_policy_summary(
    text: str,
    llm_extractor: Callable[[str], LlmPolicySummary | None]
    | None = extract_policy_summary_with_llm,
) -> PolicySummary:
    summary = extract_local_policy_summary(text)
    masked_text = mask_demographic_identifiers(text)

    if llm_extractor and _needs_llm_fill(summary):
        _merge_missing_llm_fields(summary, llm_extractor(masked_text), text)

    classification = classify_policy(text=masked_text, product_name=summary.get("상품명"))
    summary["보험분류"] = classification["보험분류"]
    summary["상품태그"] = classification["상품태그"]
    return summary


def _needs_llm_fill(summary: PolicySummary) -> bool:
    return any(field not in summary for field in _LLM_TRIGGER_FIELDS)


def _merge_missing_llm_fields(
    summary: PolicySummary, llm_summary: LlmPolicySummary | None, text: str
) -> None:
    if not llm_summary:
        return

    for key in _LLM_FILLABLE_FIELDS:
        if key in summary or key not in llm_summary:
            continue
        value = llm_summary[key]  # type: ignore[literal-required]

        if key in _GROUNDED_LLM_FIELDS:
            if not isinstance(value, str):
                continue
            grounded = (
                insurer_name_is_grounded(value, text)
                if key == "보험사"
                else wording_grounded(value, text)
            )
            if not grounded:
                continue

        if key == "차량정보":
            if not isinstance(value, dict):
                continue
            plate_number = value.get("차량번호")
            if isinstance(plate_number, str) and not wording_grounded(plate_number, text):
                continue

        summary[key] = value  # type: ignore[literal-required]
