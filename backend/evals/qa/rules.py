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

# A won amount in Korean prose is one or more digit+unit segments closed by
# 원: "42,000원", "2,000만원", "4만 2천원", "1억 2,000만원", "6,000만 원".
# Every leading segment must carry a unit (a bare "1,000 2,000원" is two
# amounts, not one), only the final segment may drop it, and spaces may
# appear anywhere. Capturing only the digits next to the final unit -- what
# an earlier version did -- read "4만 2천원" as 2,000원 and "1억 2,000만원"
# as 2,000만원, both misgrounding the figure in opposite directions.
_UNIT_MULTIPLIERS = {
    "억": 100_000_000,
    "천만": 10_000_000,
    "백만": 1_000_000,
    "십만": 100_000,
    "만": 10_000,
    "천": 1_000,
    "백": 100,
}
# Longest unit first so "천만" is not consumed as 천.
_UNIT_ALTERNATION = "|".join(sorted(_UNIT_MULTIPLIERS, key=len, reverse=True))
_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_AMOUNT_RE = re.compile(
    rf"(?:{_NUMBER}\s*(?:{_UNIT_ALTERNATION})\s*)*{_NUMBER}\s*(?:{_UNIT_ALTERNATION})?\s*원"
)
_AMOUNT_SEGMENT_RE = re.compile(rf"({_NUMBER})\s*({_UNIT_ALTERNATION})?")

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

    if turn.get("expect_source") and not _any_source_named(outcome):
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


# A handful of product names are literally the generic name of an insurance
# line ("실손의료보험" names a whole category, not one contract). Mentioning
# such a name reads as talking about the product type, not citing which
# uploaded policy a fact came from, so it cannot satisfy expect_source on
# its own. Eval-only vocabulary, same spirit as _PRONOUN_LEAK_RE above.
_GENERIC_PRODUCT_NAMES = frozenset(
    {
        "실손보험",
        "실손의료보험",
        "실손의료비보험",
        "자동차보험",
        "운전자보험",
        "여행자보험",
        "화재보험",
        "암보험",
        "건강보험",
        "종신보험",
        "정기보험",
        "치아보험",
        "어린이보험",
    }
)


def _any_source_named(outcome: TurnOutcome) -> bool:
    # A distinctive product name ("Hicar 다이렉트") identifies the source just
    # as unambiguously as the insurer name ("현대해상") -- citing either
    # counts. A product whose name is a generic line-of-business term does
    # not, because "실손의료보험은 비례보상이에요" cites nothing.
    insurers = {policy.기본정보.보험사 for policy in outcome.policies if policy.기본정보.보험사}
    products = {
        product
        for policy in outcome.policies
        if (product := policy.기본정보.상품명)
        and product.replace(" ", "") not in _GENERIC_PRODUCT_NAMES
    }
    return any(name in outcome.answer for name in insurers | products)


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
    """Convert one amount expression to won, summing its segments.

    "4만 2천원" is 4×10,000 + 2×1,000 = 42,000; a segment without a unit
    (the "42,000" in "42,000원") contributes its digits as-is.
    """

    total = 0.0
    for digits, unit in _AMOUNT_SEGMENT_RE.findall(text):
        try:
            number = float(digits.replace(",", ""))
        except ValueError:
            return None
        total += number * _UNIT_MULTIPLIERS.get(unit, 1)
    return int(total) if total.is_integer() else None


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
