"""Grounding checks for model-written QA answers."""

import re
from decimal import Decimal

from app.modules.consultation.contracts import ConsultationEvidence

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_MAGNITUDE = r"억|천만|백만|십만|만|천"
_COUNTER_UNIT = r"%|퍼센트|세|건|종|개|영업일|일|주|개월|월|년|회|배"
# Hangul numerals (삼천만원 등). We do not fully parse these — a detected
# hangul money expression is treated as unverifiable (fail-closed) below.
# Standard Korean spacing puts a space before the bound noun 원 (삼천만 원),
# so allow optional whitespace; otherwise a spaced amount escapes detection
# and fails open.
_HANGUL_MONEY = r"[영일이삼사오육칠팔구십백천만억]+\s*원"

# A single pattern that spots every numeric claim. Money alternatives come
# first so a magnitude/원 token is never mistaken for a counter:
#   1. compound/bare magnitude amount (1억2천만원, 3000만) — 원 optional
#   2. plain 원 amount (30,000,000원)
#   3. hangul money (삼천만원)
#   4. counters/ratios (90일, 50%, 2건) — behaviour unchanged
NUMERIC_CLAIM = re.compile(
    rf"(?:{_NUMBER}\s*(?:{_MAGNITUDE})\s*)+원?"
    rf"|{_NUMBER}\s*원"
    rf"|{_HANGUL_MONEY}"
    rf"|{_NUMBER}\s*(?:{_COUNTER_UNIT})"
)
# A claim is money when it ends in 원 or in a bare magnitude unit; anything
# else (건/일/세/%/…) is a counter and keeps its literal form.
_MONEY_SUFFIX = re.compile(rf"(?:원|{_MAGNITUDE})$")
# An ASCII money core is a chain of ASCII-digit terms, each optionally scaled
# by a magnitude unit. Anything that is not fully this shape (hangul numerals,
# stray glyphs) cannot be normalized and is treated as unverifiable.
_ASCII_MONEY_CORE = re.compile(rf"(?:\d+(?:\.\d+)?(?:{_MAGNITUDE})?)+")
# Positional tokens of a validated money core: an ASCII number or a single
# magnitude character. 천/백/십 are sub-multipliers inside the current 만/억
# group; 만/억 flush the accumulated group. Splitting into single units (rather
# than compound 천만/백만) is what makes 2천5백만 parse as (2천+5백)×만.
_MONEY_TOKEN = re.compile(r"\d+(?:\.\d+)?|억|만|천|백|십")
_SUB_UNIT: dict[str, int] = {"천": 1_000, "백": 100, "십": 10}
_GROUP_UNIT: dict[str, int] = {"만": 10_000, "억": 100_000_000}


def numeric_claims_are_grounded(
    answer: str,
    authoritative_answer: str,
    evidence: tuple[ConsultationEvidence, ...],
) -> bool:
    claims = _extract_claims(answer)
    if not claims:
        return True

    source = "\n".join([authoritative_answer, *(item.fact for item in evidence)])
    grounded = _extract_claims(source)
    return claims <= grounded


def numeric_claims_grounded_in_sources(
    answer: str,
    authoritative_answers: list[str],
    evidence: tuple[ConsultationEvidence, ...],
) -> bool:
    """Numbers in `answer` must all appear across the union of sources."""

    combined_authoritative = "\n".join(authoritative_answers)
    return numeric_claims_are_grounded(answer, combined_authoritative, evidence)


def _extract_claims(text: str) -> set[str]:
    return {_normalize_numeric_claim(match.group()) for match in NUMERIC_CLAIM.finditer(text)}


def _normalize_numeric_claim(value: str) -> str:
    compact = re.sub(r"[\s,]", "", value)
    if _MONEY_SUFFIX.search(compact) is None:
        return compact
    return _normalize_money(compact)


def _normalize_money(compact: str) -> str:
    core = compact[:-1] if compact.endswith("원") else compact

    # Only a pure ASCII-magnitude core can be summed to a comparable value.
    # Hangul numerals (삼천만원) or any other shape keep the raw token so the
    # subset check fails unless a source states it verbatim (fail-closed — an
    # unverifiable money expression is never treated as grounded).
    if _ASCII_MONEY_CORE.fullmatch(core) is None:
        return compact

    total = _sum_money_core(core)
    if total == total.to_integral_value():
        return f"{int(total)}원"
    return f"{total.normalize()}원"


def _sum_money_core(core: str) -> Decimal:
    """Sum a validated positional Korean money core to a comparable value.

    천/백/십 scale the pending number within the current group (2천 → 2000,
    5백 → 500); 만 flushes the group (×10,000) and 억 promotes everything
    accumulated so far (×100,000,000). So 2천5백만 → (2000+500)×10,000 and
    1억2천5백만 → 100,000,000 + 25,000,000. Numbers are always explicit ASCII
    digits here, guaranteed by the _ASCII_MONEY_CORE gate.
    """
    total = Decimal(0)  # flushed at 억 boundaries and above
    section = Decimal(0)  # accumulation below the current 만 group
    pending: Decimal | None = None

    for match in _MONEY_TOKEN.finditer(core):
        token = match.group()
        if token in _SUB_UNIT:
            base = pending if pending is not None else Decimal(1)
            section += base * _SUB_UNIT[token]
            pending = None
        elif token == "만":
            section += pending if pending is not None else Decimal(0)
            total += section * _GROUP_UNIT["만"]
            section = Decimal(0)
            pending = None
        elif token == "억":
            carried = total + section + (pending if pending is not None else Decimal(0))
            total = carried * _GROUP_UNIT["억"]
            section = Decimal(0)
            pending = None
        else:
            pending = Decimal(token)

    return total + section + (pending if pending is not None else Decimal(0))
