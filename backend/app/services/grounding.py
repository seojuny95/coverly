"""Anti-hallucination grounding shared by coverage extraction.

A digital policy has an exact text layer, so anything we present as the
policy's own content must appear in the extraction source:

- Amounts: the value *with its unit*, compared whitespace/comma-insensitively.
  Matching the whole value (not a concatenated digit blob) stops a hallucinated
  amount from passing just because its digits are a substring of unrelated
  numbers (e.g. "23원" against "12원 34원"). An amount that does not appear is
  demoted to 확인필요 instead of asserted. Some tables declare the unit once in
  the header ("가입금액 (만원)") and print bare numbers in cells; make the unit
  explicit so the display is unambiguous.
- Wording (보장내용): a cell's text is a contiguous run in the source, so a
  verbatim transcription matches once whitespace is removed; a paraphrase or
  hallucination does not.
"""

import re

AMOUNT_UNVERIFIED = "확인필요"

_MAN_UNIT_HEADER = re.compile(r"\(\s*(?:단위\s*[:：]?\s*)?만원\s*\)|단위\s*[:：]\s*만원")
_BARE_AMOUNT = re.compile(r"^\d[\d,]*$")
# An amount that already carries an explicit unit (…원/억/만/천). Its presence in
# the source means the source mixes units, so a bare value must not be assumed 만원.
_EXPLICIT_UNIT_AMOUNT = re.compile(r"\d[\d,]*\s*(?:억|만|천|원)")


def wording_grounded(detail: str, source: str) -> bool:
    """True if the wording appears in the source (whitespace-insensitive)."""
    return re.sub(r"\s", "", detail) in re.sub(r"\s", "", source)


def _norm(text: str) -> str:
    """Drop whitespace and thousands separators; keep digits, units, and words."""
    return re.sub(r"[\s,]", "", text)


def _number_tokens(text: str) -> set[str]:
    """Digit strings of each contiguous number in the text (commas removed)."""
    return {match.replace(",", "") for match in re.findall(r"\d[\d,]*", text)}


def _is_grounded(cleaned: str, source: str) -> bool:
    """True if the amount's value+unit appears in the source, or its exact number
    token does. Token match tolerates a unit char the LLM added/dropped; both
    reject a value whose digits are only a substring across unrelated numbers."""
    digits = cleaned.replace(",", "")
    if not any(ch.isdigit() for ch in digits):
        return True  # 무한·한도 … — nothing numeric to hallucinate
    return _norm(cleaned) in _norm(source) or re.sub(r"\D", "", cleaned) in _number_tokens(source)


def normalize_amount(value: str, source: str) -> str:
    """Grounded display amount: verbatim value, 만원-unit made explicit, or 확인필요."""
    cleaned = value.strip()
    if not cleaned:
        return AMOUNT_UNVERIFIED
    if not _is_grounded(cleaned, source):
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
