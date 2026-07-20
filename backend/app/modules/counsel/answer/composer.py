"""Compose counsel text from deterministic fact execution."""

from collections.abc import Iterable

from app.modules.counsel.answer.executor import FactExecution, FactTaskResult
from app.modules.counsel.facts.coverages import (
    CoverageMatch,
    CoverageNameInfo,
    UnmatchedCoverageName,
)
from app.modules.counsel.facts.policies import PolicyFact
from app.modules.reference_data.contracts import ClaimChannelMedicalIndemnity

# coverage_list exists so the agent can find the exact spelling of a coverage.
# A real portfolio holds around eighty of them, and printing that catalog answers
# no question the user asked, so it is written for the agent only.
_AGENT_ONLY_TASKS: frozenset[str] = frozenset({"coverage_list"})


def compose_fact_answer(execution: FactExecution) -> str | None:
    """Render the facts the user should see."""

    return _render(
        result for result in execution.results if result.task.kind not in _AGENT_ONLY_TASKS
    )


def compose_agent_facts(execution: FactExecution) -> str | None:
    """Render every resolved fact, including the ones kept off the screen."""

    return _render(execution.results)


def _render(results: Iterable[FactTaskResult]) -> str | None:
    sections = [_compose_result(result) for result in results]
    answer = "\n\n".join(section for section in sections if section)
    return answer or None


def _compose_result(result: FactTaskResult) -> str:
    if result.task.kind == "policy_count" and result.policy_list is not None:
        return f"현재 업로드된 보험은 {result.policy_list.count}건이에요."
    if result.task.kind == "policy_list" and result.policy_list is not None:
        return _policy_list_answer(result.policy_list.policies)
    if result.task.kind == "coverage_list" and result.coverage_names is not None:
        return _coverage_list_answer(result.coverage_names)
    if result.task.kind == "coverage_lookup" and result.coverage_lookup is not None:
        return _coverage_lookup_answer(
            result.coverage_lookup.matches,
            result.coverage_lookup.unmatched,
        )
    if result.task.kind == "coverage_total" and result.coverage_total is not None:
        return _coverage_total_answer(result)
    if result.task.kind == "overlap_check" and result.overlaps is not None:
        return _overlap_answer(result)
    if result.task.kind == "claim_channel" and result.claim_channels is not None:
        return _claim_channel_answer(result)
    if result.task.kind == "portfolio_review" and result.portfolio_bundle is not None:
        return _portfolio_review_answer(result)
    return ""


def _policy_list_answer(policies: list[PolicyFact]) -> str:
    if not policies:
        return "현재 업로드된 보험은 없어요."
    lines = []
    for policy in policies:
        info = policy.기본정보
        insurer = info.보험사 or "보험사 미확인"
        product = info.상품명 or "상품명 미확인"
        lines.append(f"- {insurer} · {product}")
    return "현재 확인된 보험은 다음과 같아요.\n" + "\n".join(lines)


def _coverage_list_answer(coverage_names: list[CoverageNameInfo]) -> str:
    if not coverage_names:
        return "현재 자료에서 확인된 담보가 없어요."
    lines = [f"- {item.담보명}" for item in coverage_names]
    return "현재 확인된 담보명은 다음과 같아요.\n" + "\n".join(lines)


def _coverage_lookup_answer(
    matches: list[CoverageMatch],
    unmatched: list[UnmatchedCoverageName],
) -> str:
    lines: list[str] = []
    if matches:
        lines.append("현재 자료에서 확인된 담보예요.")
        for match in matches:
            owner = " · ".join(part for part in (match.보험사, match.상품명) if part)
            prefix = f"{owner}의 " if owner else ""
            lines.append(f"- {prefix}{match.담보명}: {match.가입금액}")
            explanation = match.보장내용 or match.해설
            if explanation:
                lines.append(f"  - 설명: {explanation}")
    lines.extend(_unmatched_lines(unmatched))
    return "\n".join(lines) if lines else "질문한 담보를 현재 자료에서 확인하지 못했어요."


def _coverage_total_answer(result: FactTaskResult) -> str:
    total = result.coverage_total
    if total is None:
        return ""

    if not total.included:
        # Without a single confirmed amount there is nothing to add up. Saying "0원"
        # would state a total the data does not support.
        lines = ["합산할 담보를 현재 자료에서 확인하지 못했어요."]
        lines.extend(_unmatched_lines(total.unmatched))
        return "\n".join(lines)

    lines = [
        f"확인 가능한 정액형 가입금액 합계는 {total.total:,}원이에요.",
        "합산에 포함한 담보:",
    ]
    for item in total.included:
        owner = " · ".join(part for part in (item.보험사, item.상품명) if part)
        lines.append(f"- {owner} · {item.담보명}: {item.가입금액}")
    if total.excluded:
        lines.append("합산에서 제외한 담보:")
        for excluded in total.excluded:
            lines.append(f"- {excluded.담보명}: {excluded.reason}")
    lines.extend(_unmatched_lines(total.unmatched))
    return "\n".join(lines)


def _overlap_answer(result: FactTaskResult) -> str:
    """Name the contracts that share a coverage.

    A row count leaves the reader to guess what the rows are; the amounts and
    the insurer are what tells them whether the overlap matters.
    """

    overlaps = result.overlaps or []
    if not overlaps:
        return "현재 자료에서는 여러 계약에 걸쳐 겹치는 담보가 없어요."

    lines = ["여러 계약에서 함께 확인된 담보예요."]
    for item in overlaps:
        lines.append(f"- {item.담보명}")
        for entry in item.policies:
            owner = " · ".join(part for part in (entry.보험사, entry.상품명) if part)
            amount = entry.가입금액 or "가입금액 미확인"
            lines.append(f"  - {owner or '보험사 미확인'}: {amount}")
    return "\n".join(lines)


def _claim_channel_answer(result: FactTaskResult) -> str:
    channels = result.claim_channels
    if channels is None:
        return ""
    lines: list[str] = []
    if channels.channels.insurers:
        lines.append("확인된 보험사 청구 채널이에요.")
        for insurer in channels.channels.insurers:
            lines.append(f"- {insurer.name}: {insurer.customer_center or '고객센터 미확인'}")
    lines.extend(_medical_indemnity_lines(channels.channels.medical_indemnity))
    lines.extend(_unmatched_lines(channels.unmatched))
    return "\n".join(lines) if lines else "청구 채널을 확인할 담보를 현재 자료에서 찾지 못했어요."


def _medical_indemnity_lines(service: ClaimChannelMedicalIndemnity | None) -> list[str]:
    """Render the verified 실손 claim service, the same one the analysis screen shows."""

    if service is None:
        return []

    lines = [f"실손의료비는 {service.name}로도 청구할 수 있어요."]
    if service.description:
        lines.append(f"- {service.description}")
    if service.call_center:
        lines.append(f"- 고객센터: {service.call_center}")
    for link in service.links:
        lines.append(f"- {link.label}: {link.url}")
    return lines


def _portfolio_review_answer(result: FactTaskResult) -> str:
    bundle = result.portfolio_bundle
    if bundle is None:
        return ""
    lines = [
        f"월납으로 확인된 보험료 합계는 {bundle.premium.monthly_total:,}원이에요.",
        bundle.premium.note,
        "핵심 보장 체크:",
    ]
    for item in bundle.essential_coverages:
        amount = f" ({item.confirmed_amount:,}원)" if item.confirmed_amount is not None else ""
        lines.append(f"- {item.label}: {item.status_label}{amount}")
    lines.append(bundle.actual_loss_duplicates.review_note)
    return "\n".join(lines)


def _unmatched_lines(unmatched: list[UnmatchedCoverageName]) -> list[str]:
    """Lead with what was found, so a near miss does not read as a dead end.

    The coverage name is followed by punctuation rather than a 조사: a 한글
    particle changes with the last syllable of the word it attaches to, and the
    name comes from whatever the user typed, so any fixed particle is wrong
    half the time ("'암 진단'와" instead of "'암 진단'과").
    """

    lines: list[str] = []
    for item in unmatched:
        if item.candidates:
            candidates = ", ".join(item.candidates)
            lines.append(
                f"'{item.requested_name}': 이름이 똑같은 담보는 없지만, "
                f"비슷한 담보가 있어요 — {candidates}"
            )
        else:
            lines.append(f"'{item.requested_name}': 이름이 똑같은 담보를 찾지 못했어요.")
    return lines
