"""Decidable, non-LLM checks for one qa turn.

This baseline has no slot registry or structured output (see agent.py's
module docstring), so the question this module exists to answer changed:
not "did a fact segment resolve", but "did the agent write down a number
that doesn't actually exist anywhere in this turn's grounding". A number is
grounded if it appears either in the user's raw policy data or in some
tool's return value during this turn -- the latter covers a legitimate
computed total (e.g. calculate_coverage_total's sum) that never appears
verbatim in the raw per-coverage amounts.

This catches invented numbers. It does not catch misattribution (a real
amount attached to the wrong coverage) -- that needs either a human reading
the transcript or a groundedness judge, not a regex.

Grounding is compared by *parsed won value*, not string equality: raw data
stores a premium or a coverage's 가입금액숫자 as a bare int (`42000`), while
the agent (correctly) writes "42,000원" or a tool's computed total appears as
"60,000,000원" where the underlying coverages were "2,000만원"/"4,000만원".
Comparing the literal strings would flag all of these as fabricated even
though every one is grounded -- see _parse_won.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.modules.portfolio.schemas import PolicyInput

_PRONOUN_LEAK_RE = re.compile(r"그거|그것|아까|저건|저거|이거|그건")

_WON_UNITS = {
    "원": 1,
    "천원": 1_000,
    "만원": 10_000,
    "백만원": 1_000_000,
    "천만원": 10_000_000,
    "억원": 100_000_000,
}
# Longest unit first so "5천만원" reads as 천만원 rather than failing on 천원.
# Both regexes share this alternation: an amount the answer states must be
# detectable by exactly the units _parse_won can convert, or a figure phrased
# "5천만원" would never even be looked up and would pass as grounded.
_UNIT_ALTERNATION = "|".join(["억원", "천만원", "백만원", "만원", "천원", "원"])
_AMOUNT_RE = re.compile(rf"\d[\d,]*(?:\.\d+)?\s*(?:{_UNIT_ALTERNATION})")
_UNIT_SUFFIX_RE = re.compile(rf"({_UNIT_ALTERNATION})$")

# A tool serializes a computed won amount as a bare int (`total=60000000`),
# which no unit suffix would find. Only integers sitting in a field that
# actually holds an amount count: scanning every long digit run would also
# ground ids, counts and timestamps, letting a fabricated figure pass by
# coincidence.
_AMOUNT_FIELD_RE = re.compile(
    r"(?:total|금액|가입금액숫자|monthly_total|confirmed_amount"
    r"|reference_min_amount|reference_max_amount"
    r"|suggested_min_premium|suggested_max_premium)"
    r"['\"]?\s*[:=]\s*(\d+)"
)


@dataclass
class ToolCall:
    name: str
    arguments: str


@dataclass
class TurnOutcome:
    """Everything a check needs about how one turn actually ran."""

    answer: str
    tool_calls: list[ToolCall]
    tool_outputs: list[str]
    """Stringified return value of every tool called this turn -- the
    grounding surface for the fabricated-amount check, since it includes
    computed totals that never appear in the raw policy data verbatim.
    """
    policies: list[PolicyInput]


@dataclass
class CheckResult:
    failures: list[str] = field(default_factory=list)
    judge_rubrics: list[str] = field(default_factory=list)
    """Rubric keys this turn should also be scored on (dataset + auto-added)."""

    @property
    def passed(self) -> bool:
        return not self.failures


def check_turn(turn: dict[str, Any], outcome: TurnOutcome) -> CheckResult:
    result = CheckResult(judge_rubrics=list(turn.get("judge") or []))
    answer = outcome.answer

    include_all = turn.get("include_all") or []
    missing = [token for token in include_all if token not in answer]
    if missing:
        result.failures.append(f"include_all 누락: {missing}")

    include_any = turn.get("include_any") or []
    if include_any and not any(token in answer for token in include_any):
        result.failures.append(f"include_any 미충족: {include_any}")

    exclude = turn.get("exclude") or []
    forbidden = [token for token in exclude if token in answer]
    if forbidden:
        result.failures.append(f"exclude 위반: {forbidden}")

    if turn.get("expect_source") and not _any_insurer_named(outcome):
        result.failures.append("expect_source: 보험사·상품명 언급 없음")

    if turn.get("expect_in_scope") is False:
        result.judge_rubrics.append("out_of_scope_decline")

    fabricated = _fabricated_amounts(outcome)
    if fabricated:
        result.failures.append(f"근거 없는 금액 {len(fabricated)}건: {fabricated}")

    for call in outcome.tool_calls:
        leaked = _pronoun_leak(call.arguments)
        if leaked:
            result.failures.append(f"{call.name} 인자에 지시어 잔존: {leaked}")

    return result


def _any_insurer_named(outcome: TurnOutcome) -> bool:
    insurers = {policy.기본정보.보험사 for policy in outcome.policies if policy.기본정보.보험사}
    return any(insurer in outcome.answer for insurer in insurers)


def _fabricated_amounts(outcome: TurnOutcome) -> list[str]:
    known = _known_won_values(outcome)
    mentioned = _AMOUNT_RE.findall(outcome.answer)
    fabricated = []
    for text in mentioned:
        value = _parse_won(text)
        if value is not None and value not in known:
            fabricated.append(text)
    return sorted(set(fabricated))


def _known_won_values(outcome: TurnOutcome) -> set[int]:
    known: set[int] = set()

    for policy in outcome.policies:
        premium = policy.기본정보.보험료
        if premium is not None and premium.금액 is not None:
            known.add(premium.금액)
        for coverage in policy.보장목록:
            if coverage.가입금액숫자 is not None:
                known.add(coverage.가입금액숫자)
            parsed = _parse_won(coverage.가입금액)
            if parsed is not None:
                known.add(parsed)

    for tool_output in outcome.tool_outputs:
        for text in _AMOUNT_RE.findall(tool_output):
            value = _parse_won(text)
            if value is not None:
                known.add(value)
        known.update(int(match) for match in _AMOUNT_FIELD_RE.findall(tool_output))

    return known


def _parse_won(text: str) -> int | None:
    compact = re.sub(r"\s+", "", text)
    unit_match = _UNIT_SUFFIX_RE.search(compact)
    if not unit_match:
        return None
    unit = unit_match.group(1)
    number_text = compact[: unit_match.start()].replace(",", "")
    try:
        number = float(number_text)
    except ValueError:
        return None
    value = number * _WON_UNITS[unit]
    return int(value) if value.is_integer() else None


def _pronoun_leak(arguments_json: str) -> list[str]:
    try:
        parsed = json.loads(arguments_json)
    except (json.JSONDecodeError, TypeError):
        return []

    leaked: set[str] = set()
    for value in _string_values(parsed):
        leaked.update(_PRONOUN_LEAK_RE.findall(value))
    return sorted(leaked)


def _string_values(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _string_values(item)]
    if isinstance(value, list):
        return [text for item in value for text in _string_values(item)]
    return []
