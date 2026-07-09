"""Amount grounding for extracted coverages (anti-hallucination).

A digital policy has an exact text layer, so any amount we surface must appear
in the extraction source verbatim (digit-sequence match, tolerant of commas and
unit reformatting). An amount that does not is likely an LLM hallucination from
layout confusion — demote it to 확인필요 instead of asserting it.

Some tables declare the unit once in the header ("가입금액 (만원)") and print
bare numbers in cells; make the unit explicit so the display is unambiguous.
"""

import re

AMOUNT_UNVERIFIED = "확인필요"

_MAN_UNIT_HEADER = re.compile(r"\(\s*(?:단위\s*[:：]?\s*)?만원\s*\)|단위\s*[:：]\s*만원")
_BARE_AMOUNT = re.compile(r"^\d[\d,]*$")
# An amount that already carries an explicit unit (…원/억/만/천). Its presence in
# the source means the source mixes units, so a bare value must not be assumed 만원.
_EXPLICIT_UNIT_AMOUNT = re.compile(r"\d[\d,]*\s*(?:억|만|천|원)")


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def normalize_amount(value: str, source: str) -> str:
    """Grounded display amount: verbatim value, 만원-unit made explicit, or 확인필요."""
    cleaned = value.strip()
    if not cleaned:
        return AMOUNT_UNVERIFIED
    digits = _digits(cleaned)
    if digits and digits not in _digits(source):
        return AMOUNT_UNVERIFIED
    # Bare number under a 만원 header → make the unit explicit (3,000 → 3,000만원),
    # but only when the source's amounts are uniformly unit-less. If any amount
    # already carries an explicit unit, the source mixes units and assuming 만원
    # for a bare value would be 10,000x wrong (grounding violation) — keep verbatim.
    if (
        _MAN_UNIT_HEADER.search(source)
        and _BARE_AMOUNT.match(cleaned)
        and not _EXPLICIT_UNIT_AMOUNT.search(source)
    ):
        return f"{int(cleaned.replace(',', '')):,}만원"
    return cleaned
