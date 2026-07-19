"""Grounding checks for model-written QA answers."""

import re
from decimal import Decimal, InvalidOperation

from app.modules.consultation.contracts import ConsultationEvidence

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
NUMERIC_CLAIM = re.compile(
    rf"{_NUMBER}\s*(?:억|천만|백만|십만|만|천)?\s*원|"
    rf"{_NUMBER}\s*(?:%|퍼센트|세|건|종|개|영업일|일|주|개월|월|년|회|배)"
)
_WON_CLAIM = re.compile(rf"(?P<number>{_NUMBER})(?P<unit>억|천만|백만|십만|만|천)?원")
_WON_MULTIPLIERS = {
    None: 1,
    "천": 1_000,
    "만": 10_000,
    "십만": 100_000,
    "백만": 1_000_000,
    "천만": 10_000_000,
    "억": 100_000_000,
}


def numeric_claims_are_grounded(
    answer: str,
    authoritative_answer: str,
    evidence: tuple[ConsultationEvidence, ...],
) -> bool:
    claims = {_normalize_numeric_claim(item) for item in NUMERIC_CLAIM.findall(answer)}
    if not claims:
        return True

    source = "\n".join([authoritative_answer, *(item.fact for item in evidence)])
    grounded = {_normalize_numeric_claim(item) for item in NUMERIC_CLAIM.findall(source)}
    return claims <= grounded


def _normalize_numeric_claim(value: str) -> str:
    compact = re.sub(r"[\s,]", "", value)
    won = _WON_CLAIM.fullmatch(compact)
    if won is None:
        return compact
    try:
        amount = Decimal(won.group("number")) * _WON_MULTIPLIERS[won.group("unit")]
    except InvalidOperation:
        return compact
    if amount == amount.to_integral_value():
        return f"{int(amount)}원"
    return f"{amount.normalize()}원"
