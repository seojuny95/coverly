from collections.abc import Callable

from app.services.policy_classification import classify_policy
from app.services.policy_llm_extraction import LlmPolicySummary, extract_policy_summary_with_llm
from app.services.policy_summary_local import extract_local_policy_summary
from app.services.policy_summary_types import PolicySummary

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
]


def extract_policy_summary(
    text: str,
    llm_extractor: Callable[[str], LlmPolicySummary | None] | None = (
        extract_policy_summary_with_llm
    ),
) -> PolicySummary:
    summary = extract_local_policy_summary(text)

    if llm_extractor and _needs_llm_fill(summary):
        _merge_missing_llm_fields(summary, llm_extractor(text))

    classification = classify_policy(
        text=text,
        product_name=summary.get("상품명"),
    )
    summary["보험분류"] = classification["보험분류"]
    summary["상품태그"] = classification["상품태그"]

    return summary


def _needs_llm_fill(summary: PolicySummary) -> bool:
    return any(field not in summary for field in _LLM_FILLABLE_FIELDS)


def _merge_missing_llm_fields(summary: PolicySummary, llm_summary: LlmPolicySummary | None) -> None:
    if not llm_summary:
        return

    for key in _LLM_FILLABLE_FIELDS:
        if key not in summary and key in llm_summary:
            summary[key] = llm_summary[key]  # type: ignore[literal-required]
