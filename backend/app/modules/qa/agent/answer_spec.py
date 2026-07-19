"""Grounded answer spec and confirmed-amount label map for the streaming compose step.

The compose step inserts numeric amounts as placeholders filled from CONFIRMED
values so the model cannot fabricate them. `build_amount_label_map` assigns a
stable label to each confirmed amount found in tool-result evidence; the
`GroundedAnswerSpec` dataclass is the validated content a later spec builder
(Task 4) will hand to the compose step.
"""

from dataclasses import dataclass
from typing import Literal

from app.modules.qa.agent.contracts import RegisteredToolResult
from app.modules.qa.schemas import AnswerCitation, PortfolioQuestionResponse
from app.modules.reference_data.contracts import ClaimChannelBlock

SpecMode = Literal["grounded", "general_guidance", "insufficient", "out_of_scope"]


@dataclass(frozen=True)
class GroundedAnswerSpec:
    mode: SpecMode
    facts: tuple[str, ...]
    amounts: dict[str, str]
    grounding_sources: tuple[str, ...]
    citations: list[AnswerCitation]
    limitations: list[str]
    claim_channels: ClaimChannelBlock | None


def build_amount_label_map(results: list[RegisteredToolResult]) -> dict[str, str]:
    """Assign stable labels to each confirmed numeric amount from tool evidence."""
    label_map: dict[str, str] = {}
    next_index = 1

    for result in results:
        for evidence in result.evidence:
            if evidence.amount is None:
                continue
            label = f"amt{next_index}"
            label_map[label] = f"{evidence.amount:,}원"
            next_index += 1

    return label_map


def spec_mode_for(status: str, has_results: bool) -> SpecMode:
    """Derive the compose mode from the validated status and tool results.

    An answered response with grounded tool results is fully grounded; without
    results it degrades to general guidance. Missing data is insufficient, a
    refusal is out of scope, and a clarify prompt is treated as general guidance.
    """
    if status == "answered":
        return "grounded" if has_results else "general_guidance"
    if status == "no_data":
        return "insufficient"
    if status == "refused":
        return "out_of_scope"
    return "general_guidance"


def _placeholderize(text: str, amounts: dict[str, str]) -> str:
    """Replace each confirmed amount value with its ``{{label}}`` placeholder.

    Longest values are replaced first so a shorter value that is a substring of a
    longer one cannot corrupt the longer match.
    """
    result = text
    for label, value in sorted(amounts.items(), key=lambda kv: len(kv[1]), reverse=True):
        result = result.replace(value, f"{{{{{label}}}}}")
    return result


def build_answer_spec(
    validated: PortfolioQuestionResponse,
    results: list[RegisteredToolResult],
) -> GroundedAnswerSpec:
    """Turn a validated response plus tool results into a compose spec.

    ``facts`` is the validated answer with each confirmed amount swapped for its
    ``{{label}}`` placeholder, so the model re-expresses facts without touching the
    numbers. The original real-number answer and each tool answer are kept in
    ``grounding_sources`` for quoted-number verification.
    """
    amounts = build_amount_label_map(results)

    facts = (_placeholderize(validated.answer, amounts),)

    grounding_sources = (validated.answer, *(r.response.answer for r in results))

    return GroundedAnswerSpec(
        mode=spec_mode_for(validated.status, bool(results)),
        facts=facts,
        amounts=amounts,
        grounding_sources=grounding_sources,
        citations=validated.citations,
        limitations=validated.limitations,
        claim_channels=validated.claim_channels,
    )
