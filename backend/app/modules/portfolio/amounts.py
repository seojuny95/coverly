"""Shared parsing helpers for portfolio coverage amounts and labels."""

import re

from app.modules.portfolio.schemas import CoverageInput

_UNITS = {
    "원": 1,
    "천원": 1_000,
    "만원": 10_000,
    "백만원": 1_000_000,
    "천만원": 10_000_000,
    "억원": 100_000_000,
}


def parse_amount(coverage: CoverageInput) -> int | None:
    if coverage.가입금액숫자 is not None:
        return coverage.가입금액숫자
    compact = re.sub(r"\s+", "", coverage.가입금액).replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(억원|천만원|백만원|만원|천원|원)", compact)
    if match is None:
        return None
    amount = float(match.group(1)) * _UNITS[match.group(2)]
    return int(amount) if amount.is_integer() else None


def normalize(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()


def normalized_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(normalize(term) for term in terms)
