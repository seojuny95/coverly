"""Ask the user back when the turn cannot be resolved as it stands.

The planner can tell that a question needs narrowing, but only the executed
facts know what to narrow it to. Composing the question here keeps that
decision next to the evidence instead of leaving it to the agent.
"""

from app.modules.counsel.answer.executor import FactExecution
from app.modules.counsel.facts.coverages import UnmatchedCoverageName

_NOTHING_TO_NARROW = (
    "담보 이름이나 상황을 알려주시면 가입하신 내용에서 찾아볼게요. 어떤 보장을 확인해 드릴까요?"
)


def compose_clarify_question(execution: FactExecution) -> str | None:
    """Return the question to ask back, or None when nothing needs narrowing."""

    unmatched = _unmatched_with_candidates(execution)
    if unmatched:
        return _candidate_question(unmatched)

    if not execution.results:
        return _NOTHING_TO_NARROW

    # A name that resolved to nothing and suggested nothing is not something we can
    # usefully ask about -- "심장 쪽" matches no coverage by spelling, but the agent
    # can still recognise it as 허혈성심질환. Asking a generic question here would
    # throw that away.
    return None


def _unmatched_with_candidates(execution: FactExecution) -> list[UnmatchedCoverageName]:
    found: list[UnmatchedCoverageName] = []
    for result in execution.results:
        for source in (result.coverage_lookup, result.coverage_total, result.claim_channels):
            if source is None:
                continue
            found.extend(item for item in source.unmatched if item.candidates)
    return found


def _candidate_question(unmatched: list[UnmatchedCoverageName]) -> str:
    """Ask which coverage was meant, listing the near misses.

    Neither the requested name nor the last candidate takes a 조사: both come
    from data, and a 한글 particle changes with the last syllable of the word
    before it, so a fixed one is wrong half the time.
    """

    lines: list[str] = []
    for item in unmatched:
        candidates = ", ".join(item.candidates)
        lines.append(
            f"'{item.requested_name}'에 가까운 담보예요 — {candidates}. "
            "어느 쪽을 말씀하시는 걸까요?"
        )
    return "\n".join(lines)
