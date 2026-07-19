"""Agent SDK tools for structured coverage lookup and calculation."""

from agents import RunContextWrapper, function_tool

from app.modules.consultation.contracts import ConsultationEvidence
from app.modules.coverage.matching import canonicalize_coverage_name
from app.modules.portfolio.schemas import CoverageTotalItem
from app.modules.qa.agent.contracts import GroundedToolAnswer, QaAgentDependencies
from app.modules.qa.tools.evidence import (
    coverage_evidence_by_names,
    coverage_explanations,
    overlap_evidence,
)
from app.modules.qa.tools.responses import portfolio_response


@function_tool
def find_coverages(
    wrapper: RunContextWrapper[QaAgentDependencies],
    coverage_names: list[str],
) -> GroundedToolAnswer:
    """Find held coverages by model-resolved coverage, insurer, or product names.

    Args:
        coverage_names: Concrete names inferred from the request, not intent keywords.
    """

    dependencies = wrapper.context
    context = dependencies.context
    facts_evidence = coverage_evidence_by_names(context, coverage_names)
    explanations = coverage_explanations(context, coverage_names)
    existing_ids = {item.id for item in facts_evidence}
    new_explanations = tuple(item for item in explanations if item.id not in existing_ids)
    evidence = facts_evidence + new_explanations
    if not evidence:
        return dependencies.unmatched(
            "coverage_lookup",
            "No uploaded-policy identity matched the supplied names.",
        )
    answer = _coverage_lookup_answer(facts_evidence, new_explanations)
    return dependencies.register(
        "coverage_lookup",
        portfolio_response(context, answer, evidence),
        evidence=evidence,
        trust_level="deterministic",
    )


def _coverage_lookup_answer(
    facts_evidence: tuple[ConsultationEvidence, ...],
    new_explanations: tuple[ConsultationEvidence, ...],
) -> str:
    """Build the find_coverages answer without a dangling empty facts header.

    facts_evidence and new_explanations can each be empty, but not both (the
    caller returns unmatched before reaching here in that case).
    """

    if facts_evidence:
        answer = "업로드 증권에서 다음 내용을 확인했습니다.\n\n" + "\n".join(
            f"- {item.fact}" for item in facts_evidence
        )
        if new_explanations:
            answer += "\n\n담보 설명:\n" + "\n".join(f"- {item.fact}" for item in new_explanations)
        return answer

    return "업로드 증권의 담보 설명이에요.\n\n" + "\n".join(
        f"- {item.fact}" for item in new_explanations
    )


@function_tool
def calculate_coverage_total(
    wrapper: RunContextWrapper[QaAgentDependencies],
    coverage_names: list[str],
    all_fixed_coverages: bool = False,
    combine_multiple_coverages: bool = False,
) -> GroundedToolAnswer:
    """Calculate confirmed fixed-benefit totals for explicit coverage identities.

    Args:
        coverage_names: Concrete coverage names whose confirmed amounts should be summed.
        all_fixed_coverages: True only when the user explicitly asks for the whole fixed total.
        combine_multiple_coverages: True only when the user explicitly names multiple coverages.
    """

    dependencies = wrapper.context
    context = dependencies.context
    totals = context.facts.coverage_summary.totals
    selected = totals if all_fixed_coverages else _matching_totals(totals, coverage_names)
    if not selected:
        return dependencies.unmatched(
            "coverage_total",
            "No calculable coverage total matched.",
        )
    if len(selected) > 1 and not (all_fixed_coverages or combine_multiple_coverages):
        return dependencies.unmatched(
            "coverage_total",
            (
                "Multiple coverage identities matched. Retry with only the coverage explicitly "
                "requested by the user."
            ),
        )

    evidence = coverage_evidence_by_names(context, [item.display_name for item in selected])
    total_amount = sum(item.total_amount for item in selected)
    if len(selected) == 1:
        answer = (
            f"{selected[0].display_name}의 확인 가능한 가입금액 합계는 {total_amount:,}원입니다."
        )
    else:
        details = "\n".join(f"- {item.display_name}: {item.total_amount:,}원" for item in selected)
        answer = (
            f"확인 가능한 정액형 담보 {len(selected)}종의 합계는 {total_amount:,}원입니다."
            f"\n\n{details}"
        )
    return dependencies.register(
        "coverage_total",
        portfolio_response(context, answer, evidence),
        evidence=evidence,
        trust_level="deterministic",
    )


@function_tool
def find_overlapping_coverages(
    wrapper: RunContextWrapper[QaAgentDependencies],
) -> GroundedToolAnswer:
    """Find overlaps from structured duplicate flags across all uploaded policies."""

    dependencies = wrapper.context
    context = dependencies.context
    evidence = overlap_evidence(context)
    if not evidence:
        return dependencies.unmatched(
            "coverage_overlap",
            "No overlap evidence was available.",
        )
    answer = "업로드 증권 전체의 중복 집계 결과입니다.\n\n" + "\n".join(
        f"- {item.fact}" for item in evidence
    )
    return dependencies.register(
        "coverage_overlap",
        portfolio_response(context, answer, evidence),
        evidence=evidence,
        trust_level="deterministic",
    )


def _matching_totals(
    totals: list[CoverageTotalItem],
    coverage_names: list[str],
) -> list[CoverageTotalItem]:
    requested = {
        canonicalize_coverage_name(name).normalized_key for name in coverage_names if name.strip()
    }
    return [
        item
        for item in totals
        if item.normalized_name in requested
        or canonicalize_coverage_name(item.display_name.split("(")[0]).normalized_key in requested
    ]
