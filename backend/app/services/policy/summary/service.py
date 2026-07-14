"""Extract a display-ready policy summary from parsed PDF text.

Combines three extraction layers into one flat module:
  1. Local (regex) extraction — fast, deterministic, works offline.
  2. LLM extraction — fills fields the regex layer could not find.
  3. Classification merge — attaches 보험분류/상품태그 via `classify_policy`.
"""

import re
from collections.abc import Callable
from functools import lru_cache

from pydantic import BaseModel, ConfigDict

from app.services.grounding import wording_grounded
from app.services.llm import JsonCompleter, structured_completer
from app.services.paths import SERVICE_DATA_DIR
from app.services.policy.classification import classify_policy
from app.services.policy.demographics import (
    extract_insured_demographics,
    mask_demographic_identifiers,
)
from app.services.policy.models import (
    CoveragePeriod,
    PolicyCoreSummary,
    PolicySummary,
    PremiumSummary,
    VehicleInfo,
)
from app.services.reference_data import load_reference_data
from app.settings import get_settings

LlmPolicySummary = PolicyCoreSummary


# --------------------------------------------------------------------------
# Local (regex) extraction
# --------------------------------------------------------------------------

_FIELD_LABELS: dict[str, list[str]] = {
    "보험사": ["보험사", "회사명", "발행회사"],
    "상품명": ["상품명", "상품명칭", "플랜명", "보험종목"],
    "증권번호": ["증권번호", "보험증권번호", "계약번호"],
    "계약자": ["보험계약자", "계약자"],
    "피보험자": ["기명피보험자", "피보험자성명", "(주)피보험자", "피보험자"],
}

_DATE_VALUE_PARTS_PATTERN = r"(20\d{2})[.\-/년 ]\s*(\d{1,2})[.\-/월 ]\s*(\d{1,2})"
_DATE_VALUE_PATTERN = r"(?:20\d{2})[.\-/년 ]\s*\d{1,2}[.\-/월 ]\s*\d{1,2}(?:일)?"
_POLICY_NUMBER_VALUE_PATTERN = r"[A-Z0-9*][A-Z0-9*\-]{5,}"
_PERSON_NAME_VALUE_PATTERN = r"[가-힣A-Za-z]{2,}"
_PERSON_NAME_WITH_OPTIONAL_PAREN_PATTERN = rf"{_PERSON_NAME_VALUE_PATTERN}(?:\([^)]+\))?"
_AMOUNT_VALUE_PATTERN = r"(\d[\d,]*)\s*원"
_PREMIUM_WITH_CYCLE_PATTERN = r"([\d,]+)원\s*(월납|연납|일시납)"
_SECTION_BOUNDARIES = [
    "계약사항",
    "만기보험금수익자",
    "판매플랜",
    "상해급수",
    "직업/직무",
    "운행차량",
    "이륜차부담보특약",
    "사망보험금수익자",
    "생존보험금수익자",
    "담보정보",
    "가입정보",
    "보험기간/납입기간",
]
_PRODUCT_NAME_PATTERNS = [
    r"보험종목\s*(무배당.+?)\s*증권번호",
    r"보험증권(?:\[보험가입증서\])?\s*(무배당.+?)(?:\n|\[모바일약관\]|계약자)",
]
_POLICY_NUMBER_EXTRACTION_PATTERNS = [
    rf"계약번호\s*[:：]?\s*({_POLICY_NUMBER_VALUE_PATTERN})",
    rf"증권번호\s*[:：]?\s*({_POLICY_NUMBER_VALUE_PATTERN})",
    rf"계약자\s+[가-힣A-Za-z]+\s+증권번호\s+({_POLICY_NUMBER_VALUE_PATTERN})",
]
_POLICY_HOLDER_EXTRACTION_PATTERNS = [
    rf"보험계약자\s*({_PERSON_NAME_VALUE_PATTERN})\s*\(",
    r"계약자\s+([가-힣A-Za-z]+)\s+증권번호",
    rf"증권번호\s*{_POLICY_NUMBER_VALUE_PATTERN}\s*계약자\s*({_PERSON_NAME_VALUE_PATTERN})",
    rf"계약자\s*({_PERSON_NAME_VALUE_PATTERN})\s*\([^)]*\)\s*보험기간",
]
_INSURED_PERSON_EXTRACTION_PATTERNS = [
    r"피보험자성명\s+([가-힣A-Za-z]+)\s+피보험자번호",
    r"피보험자\s+([가-힣A-Za-z]+)\s+주민등록번호",
    rf"피보험자\s*({_PERSON_NAME_VALUE_PATTERN})\s*\(",
]


def _doubled_glyph_pattern(label: str) -> str:
    """Match a label where each character may render doubled.

    Some PDFs synthesize bold Korean text by drawing each glyph twice at a
    near-identical position; pdfplumber's text extraction then emits every
    character back-to-back twice (e.g. "납입보험료" -> "납납입입보보험험료료").
    This is a rendering/layout artifact, not an insurer-specific string, so
    every label lookup that might land on bold table text should tolerate it.
    """
    return "".join(f"{re.escape(char)}{{1,2}}" for char in label)


_PREMIUM_AMOUNT_PATTERNS = [
    rf"{_doubled_glyph_pattern('납입보험료')}\s*[:：]?\s*([\d,]+)원",
    r"1회 보험료\s*([\d,\s]+)원",
    r"납입한 보험료\s*(?:\(총보험료\)\s*)?([\d,]+)원",
    rf"{_doubled_glyph_pattern('보험료')}\s*([\d,]+)원",
]
_PAYMENT_PERIOD_PATTERNS = [
    r"\b(\d+년납)\b",
    r"\b(전기납)\b",
    r"\b(일시납)\b",
]

_INSURER_LABELS = _FIELD_LABELS["보험사"]
_PRODUCT_NAME_LABELS = _FIELD_LABELS["상품명"]
_POLICY_NUMBER_LABELS = _FIELD_LABELS["증권번호"]
_POLICY_HOLDER_LABELS = _FIELD_LABELS["계약자"]
_INSURED_PERSON_LABELS = _FIELD_LABELS["피보험자"]
_GENERIC_PRODUCT_NAMES = {"보험", "보험증권"}
_LABEL_LIKE_SUFFIXES = ("주소", "번호", "기간", "성명")
_LABEL_LIKE_SUBSTRINGS = ("피보험자", "계약자")


def _valid_person_name(candidate: str) -> bool:
    """Reject label-echoing garbage; accept only shape-valid person names.

    A value that itself looks like a table label (ends in 주소/번호/기간/성명,
    or contains 피보험자/계약자) is a two-column-table mis-parse, not a name.
    """
    if not re.fullmatch(_PERSON_NAME_WITH_OPTIONAL_PAREN_PATTERN, candidate):
        return False

    bare_name = candidate.split("(")[0].strip()
    if not bare_name or not re.fullmatch(_PERSON_NAME_VALUE_PATTERN, bare_name):
        return False

    if bare_name.endswith(_LABEL_LIKE_SUFFIXES):
        return False

    return all(token not in bare_name for token in _LABEL_LIKE_SUBSTRINGS)


def extract_local_policy_summary(text: str) -> PolicySummary:
    summary: PolicySummary = {}

    insurer_name = _extract_insurer_name(text)
    if insurer_name:
        summary["보험사"] = insurer_name

    product_name = _extract_product_name(text)
    if product_name:
        summary["상품명"] = product_name

    policy_number = _extract_policy_number(text)
    if policy_number:
        summary["증권번호"] = policy_number

    policy_holder = _extract_policy_holder(text)
    if policy_holder:
        summary["계약자"] = policy_holder

    insured_person = _extract_insured_person(text)
    if insured_person:
        summary["피보험자"] = insured_person

    coverage_period = _extract_period(text)
    if coverage_period:
        summary["보험기간"] = coverage_period

    maturity_date = _extract_maturity_date(coverage_period)
    if maturity_date:
        summary["만기일"] = maturity_date

    premium = _extract_premium(text)
    if premium:
        summary["보험료"] = premium

    payment_period = _extract_payment_period(text)
    if payment_period:
        summary["납입기간"] = payment_period

    insured_demographics = extract_insured_demographics(text)
    if insured_demographics:
        summary["피보험자정보"] = insured_demographics

    return summary


def _normalized_lines(text: str) -> list[str]:
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" :|-")


def _extract_between_markers(
    text: str,
    start_markers: list[str],
    end_markers: list[str],
) -> str | None:
    for start_marker in start_markers:
        for end_marker in end_markers:
            if start_marker == end_marker:
                continue

            match = re.search(
                rf"(?<![가-힣A-Za-z]){re.escape(start_marker)}\s*(.+?)\s*(?={re.escape(end_marker)})",
                text,
            )
            if not match:
                continue

            candidate = _clean_value(match.group(1))
            if candidate:
                return candidate

    return None


def _extract_labeled_value(text: str, labels: list[str]) -> str | None:
    lines = _normalized_lines(text)
    for index, line in enumerate(lines):
        for label in labels:
            if line == label and index + 1 < len(lines):
                candidate = _clean_value(lines[index + 1])
                if candidate:
                    return candidate

            match = re.match(rf"^{re.escape(label)}(?:\s*[:：]\s*|\s+)(.+)$", line)
            if match:
                candidate = _clean_value(match.group(1))
                if candidate:
                    return candidate

    return None


def _first_pattern_match(patterns: list[str], text: str) -> re.Match[str] | None:
    return next((match for pattern in patterns if (match := re.search(pattern, text))), None)


def _normalize_insurer_alias(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()


def match_insurer_from_text(text: str) -> str | None:
    """Return the catalog insurer whose generated/data alias appears in text."""

    contact_match = _match_insurer_by_contact_evidence(text)
    if contact_match:
        return contact_match

    normalized_text = _normalize_insurer_alias(text)
    if not normalized_text:
        return None

    for insurer, aliases in get_insurer_aliases().items():
        if any(_insurer_alias_matches(alias, text, normalized_text) for alias in aliases):
            return insurer

    return None


def _match_insurer_by_contact_evidence(text: str) -> str | None:
    normalized_text = _normalize_contact_text(text)
    digits = re.sub(r"\D", "", text)
    for insurer, domains, phones in get_insurer_contact_evidence():
        if domains and any(domain in normalized_text for domain in domains):
            return insurer
        if phones and any(phone in digits for phone in phones):
            return insurer
    return None


def _normalize_contact_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _insurer_alias_matches(alias: str, text: str, normalized_text: str) -> bool:
    normalized_alias = _normalize_insurer_alias(alias)
    if not normalized_alias:
        return False
    if len(normalized_alias) <= 2:
        tokens = {token.casefold() for token in _BRAND_TOKEN_PATTERN.findall(text)}
        return normalized_alias in tokens
    return normalized_alias in normalized_text


def _extract_insurer_name(text: str) -> str | None:
    labeled = _extract_labeled_value(text, _INSURER_LABELS)
    if labeled:
        return labeled

    return match_insurer_from_text(text)


_PRODUCT_NAME_TRAILING_LABELS = _POLICY_NUMBER_LABELS + [
    "계약자",
    "보험계약자",
    "기명피보험자",
    "보험기간",
]


def _truncate_before_trailing_label(value: str, labels: list[str]) -> str:
    """Cut a same-line value at the next field label glued onto it.

    Some layouts squeeze several fields onto one text line (e.g.
    "<상품명> 증권번호 <번호>"), so a naive "rest of line" capture pulls the
    next field's label and value in too. This is a generic same-line-fields
    layout shape, not an insurer-specific pattern.
    """
    earliest_index: int | None = None
    for label in labels:
        match = re.search(rf"\s+{re.escape(label)}\b", value)
        if match and (earliest_index is None or match.start() < earliest_index):
            earliest_index = match.start()

    if earliest_index is None:
        return value
    return _clean_value(value[:earliest_index])


def _extract_product_name(text: str) -> str | None:
    explicit_name = _extract_labeled_value(text, _PRODUCT_NAME_LABELS)
    if explicit_name:
        explicit_name = _truncate_before_trailing_label(
            explicit_name, _PRODUCT_NAME_TRAILING_LABELS
        )
    if explicit_name and explicit_name not in _GENERIC_PRODUCT_NAMES:
        return explicit_name

    for pattern in _PRODUCT_NAME_PATTERNS:
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            continue

        candidate = _clean_value(match.group(1))
        if candidate and candidate not in _GENERIC_PRODUCT_NAMES:
            return candidate

    inline_name = _extract_between_markers(
        text,
        _PRODUCT_NAME_LABELS,
        _PRODUCT_NAME_TRAILING_LABELS,
    )
    if inline_name and inline_name not in _GENERIC_PRODUCT_NAMES:
        return inline_name

    lines = _normalized_lines(text)
    for line in lines:
        candidate = _clean_value(line)
        if candidate.startswith("(무)") or candidate.startswith("무배당 "):
            return candidate

    for index, line in enumerate(lines):
        if line not in {"보험증권", "보 험 증 권"} or index + 1 >= len(lines):
            continue

        candidate = _clean_value(lines[index + 1])
        if candidate.startswith("무배당"):
            return candidate

    return None


def _is_parenthesized_id_mask(line: str, match: re.Match[str]) -> bool:
    """True when a policy-number-shaped match is actually a masked ID in parens.

    Korean policy documents commonly show a name followed by a masked
    resident-registration number in parentheses. That value
    is shape-compatible with a policy number but is wrapped tightly in
    parentheses immediately after a name — a structural signal, not an
    insurer-specific string, that distinguishes it from a real policy number.
    """
    start, end = match.start(), match.end()
    return start > 0 and line[start - 1] == "(" and end < len(line) and line[end] == ")"


def _extract_policy_number(text: str) -> str | None:
    lines = _normalized_lines(text)
    policy_number_pattern = re.compile(_POLICY_NUMBER_VALUE_PATTERN)

    for pattern in _POLICY_NUMBER_EXTRACTION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return _clean_value(match.group(1))

    inline_value = _extract_between_markers(
        text,
        _POLICY_NUMBER_LABELS,
        _POLICY_HOLDER_LABELS + _INSURED_PERSON_LABELS + ["보험기간", "보험료"],
    )
    if inline_value:
        inline_match = policy_number_pattern.search(inline_value)
        if inline_match and not _is_parenthesized_id_mask(inline_value, inline_match):
            return _clean_value(inline_match.group(0))

    for index, line in enumerate(lines):
        if "증권번호" not in line and "계약번호" not in line:
            continue
        for offset in range(1, 5):
            next_index = index + offset
            if next_index >= len(lines):
                break
            candidate_line = lines[next_index]
            candidate_match = policy_number_pattern.search(candidate_line)
            if candidate_match and not _is_parenthesized_id_mask(candidate_line, candidate_match):
                return _clean_value(candidate_match.group(0))

    labeled_value = _extract_labeled_value(text, _POLICY_NUMBER_LABELS)
    if not labeled_value:
        return None

    labeled_match = policy_number_pattern.search(labeled_value)
    return _clean_value(labeled_match.group(0)) if labeled_match else None


def _extract_policy_holder(text: str) -> str | None:
    return _extract_person_name(
        text,
        patterns=_POLICY_HOLDER_EXTRACTION_PATTERNS,
        exact_labels={"보험계약자", "계약자", "◆ 계약자"},
        inline_start_labels=["계약자"],
        inline_end_labels=["보험기간", "증권번호", "피보험자", "계약사항", "만기보험금수익자"],
        value_labels=_POLICY_HOLDER_LABELS,
    )


def _extract_insured_person(text: str) -> str | None:
    return _extract_person_name(
        text,
        patterns=_INSURED_PERSON_EXTRACTION_PATTERNS,
        exact_labels={"기명피보험자", "피보험자성명", "(주)피보험자", "피보험자"},
        inline_start_labels=_INSURED_PERSON_LABELS,
        inline_end_labels=[
            "판매플랜",
            "상해급수",
            "직업/직무",
            "운행차량",
            "보험기간",
            "가입담보",
            "증권번호",
        ],
        value_labels=_INSURED_PERSON_LABELS,
    )


def _extract_person_name(
    text: str,
    *,
    patterns: list[str],
    exact_labels: set[str],
    inline_start_labels: list[str],
    inline_end_labels: list[str],
    value_labels: list[str],
) -> str | None:
    lines = _normalized_lines(text)
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = _clean_value(match.group(1))
            normalized = _normalize_person_name(candidate)
            if normalized:
                return normalized

    for index, line in enumerate(lines):
        if line not in exact_labels:
            continue
        for offset in range(1, 3):
            next_index = index + offset
            if next_index >= len(lines):
                break
            candidate = _clean_value(lines[next_index])
            normalized = _normalize_person_name(candidate)
            if normalized:
                return normalized

    inline_value = _extract_between_markers(
        text,
        inline_start_labels,
        inline_end_labels,
    )
    if inline_value:
        inline_match = re.match(rf"({_PERSON_NAME_VALUE_PATTERN})", inline_value)
        if inline_match and _valid_person_name(inline_match.group(1)):
            return inline_match.group(1)

    labeled_value = _extract_labeled_value(text, value_labels)
    if labeled_value:
        return _normalize_person_name(labeled_value)

    return None


def _normalize_person_name(candidate: str) -> str | None:
    return candidate.split("(")[0].strip() if _valid_person_name(candidate) else None


def _normalize_date(value: str) -> str | None:
    match = re.search(_DATE_VALUE_PARTS_PATTERN, value)
    if not match:
        return None

    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _extract_period(text: str) -> CoveragePeriod | None:
    lines = _normalized_lines(text)
    collapsed = " ".join(lines)

    korean_range_match = re.search(
        r"(20\d{2})년(\d{2})월(\d{2})일\s*부터\s*(20\d{2})년(\d{2})월(\d{2})일",
        collapsed,
    )
    if korean_range_match:
        start_date = _compose_ymd(
            korean_range_match.group(1),
            korean_range_match.group(2),
            korean_range_match.group(3),
        )
        end_date = _compose_ymd(
            korean_range_match.group(4),
            korean_range_match.group(5),
            korean_range_match.group(6),
        )
        return {
            "시작일": start_date,
            "종료일": end_date,
        }

    compact_range_match = re.search(
        r"보험기간\s*[:：]?\s*(20\d{2})(\d{2})(\d{2})~(20\d{2})(\d{2})(\d{2})",
        collapsed,
    )
    if compact_range_match:
        start_date = _compose_ymd(
            compact_range_match.group(1),
            compact_range_match.group(2),
            compact_range_match.group(3),
        )
        end_date = _compose_ymd(
            compact_range_match.group(4),
            compact_range_match.group(5),
            compact_range_match.group(6),
        )
        return {
            "시작일": start_date,
            "종료일": end_date,
        }

    range_match = re.search(
        rf"보험기간\s*[:：]?\s*({_DATE_VALUE_PATTERN})\s*(?:~|-|부터)\s*({_DATE_VALUE_PATTERN})",
        collapsed,
    )
    if not range_match:
        inline_value = _extract_between_markers(collapsed, ["보험기간"], _SECTION_BOUNDARIES)
        if inline_value:
            range_match = re.search(
                rf"({_DATE_VALUE_PATTERN})\s*(?:~|-|부터)\s*({_DATE_VALUE_PATTERN})",
                inline_value,
            )
    if not range_match:
        return None

    normalized_start_date = _normalize_date(range_match.group(1))
    normalized_end_date = _normalize_date(range_match.group(2))
    if not normalized_start_date or not normalized_end_date:
        return None

    return {"시작일": normalized_start_date, "종료일": normalized_end_date}


def _compose_ymd(year: str, month: str, day: str) -> str:
    return f"{year}-{month}-{day}"


def _extract_premium(text: str) -> PremiumSummary | None:
    match = re.search(_PREMIUM_WITH_CYCLE_PATTERN, text)
    if match:
        return {
            "금액": int(match.group(1).replace(",", "")),
            "납입주기": match.group(2),
        }

    amount_match = _first_pattern_match(_PREMIUM_AMOUNT_PATTERNS, text)
    if not amount_match:
        raw_value = _extract_labeled_value(text, ["보험료", "월보험료", "납입보험료"])
        if not raw_value:
            return None
        amount_match = re.search(_AMOUNT_VALUE_PATTERN, raw_value)
        if not amount_match:
            return None
        raw_cycle_source = raw_value
    else:
        raw_cycle_source = text[max(0, amount_match.start() - 16) : amount_match.end() + 32]

    cycle = _extract_payment_cycle(raw_cycle_source)
    if not cycle:
        contract_terms = _extract_between_markers(
            text,
            ["계약사항"],
            ["만기보험금수익자", "가입정보", "보험료"],
        )
        if contract_terms:
            cycle = _extract_payment_cycle(contract_terms)

    premium_amount = int(re.sub(r"\s+", "", amount_match.group(1)).replace(",", ""))
    premium: PremiumSummary = {"금액": premium_amount}
    if cycle:
        premium["납입주기"] = cycle
    return premium


def _extract_payment_cycle(value: str) -> str:
    if "일시납" in value:
        return "일시납"
    if "연납" in value or "연 " in value:
        return "연납"
    if "월납" in value or "월 " in value:
        return "월납"
    return ""


def _extract_payment_period(text: str) -> str | None:
    match = _first_pattern_match(_PAYMENT_PERIOD_PATTERNS, text)
    if match:
        return match.group(1)

    collapsed = " ".join(_normalized_lines(text))
    contract_terms = _extract_between_markers(
        collapsed,
        ["계약사항"],
        ["만기보험금수익자", "가입정보", "보험료", "담보정보"],
    )
    if not contract_terms:
        return None

    match = _first_pattern_match(_PAYMENT_PERIOD_PATTERNS, contract_terms)
    if match:
        return match.group(1)

    return None


def _extract_maturity_date(coverage_period: CoveragePeriod | None) -> str | None:
    if coverage_period and coverage_period.get("종료일"):
        return coverage_period["종료일"]
    return None


# --------------------------------------------------------------------------
# LLM extraction
# --------------------------------------------------------------------------

_MAX_INPUT_CHARS = 30_000
_INSURER_CATALOG_PATH = SERVICE_DATA_DIR / "insurer_catalog.json"
_CLAIM_CHANNELS_PATH = SERVICE_DATA_DIR / "claim_channels.json"
_SUMMARY_STRING_FIELDS = (
    "보험사",
    "상품명",
    "증권번호",
    "계약자",
    "피보험자",
    "만기일",
    "납입기간",
)
_SYSTEM_PROMPT = (
    "너는 한국 보험증권 PDF에서 표시용 핵심 필드만 추출한다. "
    "보험사는 보험계약을 인수하거나 증권을 발행한 보험회사명이다. "
    "상품명, 브랜드명, 플랜명, 부서명, 모집/품질보증 담당자명은 보험사가 아니다. "
    "보험사는 반드시 사용자가 제공한 후보 목록 중 하나만 선택한다. "
    "회사명이 그대로 적혀 있지 않으면 문서의 단서(로고 표기, 상품 브랜드, "
    "홈페이지 주소, 콜센터 안내 등)를 후보 목록과 연결해 판단하라. "
    "그래도 어느 후보인지 확인할 수 없으면 null로 둔다."
)


class _LlmCoveragePeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    시작일: str | None
    종료일: str | None


class _LlmPremium(BaseModel):
    model_config = ConfigDict(extra="forbid")

    금액: int | None
    납입주기: str | None


class _LlmVehicleInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    차량명: str | None
    차량번호: str | None
    연식: str | None


class _LlmPolicySummaryExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    보험사: str | None
    상품명: str | None
    증권번호: str | None
    계약자: str | None
    피보험자: str | None
    보험기간: _LlmCoveragePeriod | None
    만기일: str | None
    납입기간: str | None
    보험료: _LlmPremium | None
    차량정보: _LlmVehicleInfo | None


@lru_cache
def get_insurer_candidates() -> tuple[str, ...]:
    return load_reference_data(
        "insurer_catalog", _INSURER_CATALOG_PATH, _validate_insurer_candidates
    )


def _validate_insurer_candidates(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, list):
        raise ValueError("insurer catalog must be a JSON list")

    candidates = tuple(value for value in payload if isinstance(value, str) and value.strip())
    if not candidates:
        raise ValueError("insurer catalog must contain at least one insurer")

    return candidates


@lru_cache
def get_insurer_aliases() -> dict[str, tuple[str, ...]]:
    """Generate catalog-derived insurer aliases used by local extraction."""

    aliases: dict[str, set[str]] = {
        insurer: set(_generated_insurer_aliases(insurer)) for insurer in get_insurer_candidates()
    }

    return {insurer: tuple(values) for insurer, values in aliases.items() if values}


@lru_cache
def get_insurer_contact_evidence() -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    """Return catalog insurers with official homepage domains and call-center digits."""

    payload = load_reference_data("claim_channels", _CLAIM_CHANNELS_PATH, _validate_contact_data)
    entries = payload["보험사"]

    evidence: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        insurer_name = entry.get("보험사")
        if not isinstance(insurer_name, str):
            continue

        insurer = _catalog_insurer_for_name(insurer_name)
        if insurer is None:
            continue

        domains = tuple(
            value
            for key in ("홈페이지", "청구링크", "source")
            if isinstance(entry.get(key), str)
            for value in _domain_evidence(entry[key])
        )
        phone = entry.get("고객센터")
        phones = (re.sub(r"\D", "", phone),) if isinstance(phone, str) else ()
        evidence.append((insurer, domains, tuple(value for value in phones if value)))

    return tuple(evidence)


def _validate_contact_data(payload: object) -> dict[str, list[object]]:
    if not isinstance(payload, dict):
        raise ValueError("claim channels must be an object")

    entries = payload.get("보험사")
    if not isinstance(entries, list):
        raise ValueError("claim channels must contain an insurer list")
    return {"보험사": entries}


def _domain_evidence(url: str) -> tuple[str, ...]:
    match = re.search(r"https?://([^/\s]+)", url.casefold())
    if not match:
        return ()
    host = match.group(1).removeprefix("www.")
    if "." not in host:
        return ()
    return (host,)


def _catalog_insurer_for_name(value: str) -> str | None:
    """Map a data-file display name to the canonical catalog insurer."""

    if value in get_insurer_candidates():
        return value

    normalized_value = _normalize_insurer_alias(value)
    if not normalized_value:
        return None

    for insurer, aliases in get_insurer_aliases().items():
        normalized_aliases = {_normalize_insurer_alias(alias) for alias in aliases}
        if normalized_value in normalized_aliases:
            return insurer

    return None


def _generated_insurer_aliases(insurer: str) -> tuple[str, ...]:
    """Generate generic aliases from catalog names, without insurer-specific code."""

    generated = {insurer}
    brand = insurer
    for suffix in _INSURER_NAME_SUFFIXES:
        if insurer.endswith(suffix) and len(insurer) > len(suffix):
            generated.add(insurer[: -len(suffix)])

    brand = min(generated, key=len)

    if brand.endswith("손해") and len(brand) > len("손해"):
        generated.add(f"{brand.removesuffix('손해')}손보")

    return tuple(alias for alias in generated if len(alias.strip()) >= 2)


def extract_policy_summary_with_llm(text: str) -> LlmPolicySummary | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    insurer_candidates = get_insurer_candidates()
    try:
        raw_summary = _default_summary_completer()(
            _SYSTEM_PROMPT,
            _summary_user_prompt(text, insurer_candidates),
        )
    except Exception:
        return None

    return _coerce_policy_summary(raw_summary, insurer_candidates)


@lru_cache
def _default_summary_completer() -> JsonCompleter:
    return structured_completer(_LlmPolicySummaryExtraction)


def _summary_user_prompt(text: str, insurer_candidates: tuple[str, ...]) -> str:
    insurer_list = "\n".join(f"- {insurer}" for insurer in insurer_candidates)
    truncated_text = text[:_MAX_INPUT_CHARS]

    return (
        "다음 텍스트에서 보험사, 상품명, 증권번호, 계약자, 피보험자, "
        "보험기간, 만기일, 납입기간, 보험료를 추출해.\n"
        "보험사 후보 목록:\n"
        f"{insurer_list}\n\n"
        "보험사에는 후보 목록에 없는 상품명이나 브랜드명을 넣지 마. "
        "후보 목록의 실제 보험회사와 명확히 연결되는 경우에만 후보명을 선택해.\n\n"
        "차량정보(차량명·차량번호·연식)도 추출해. 자동차보험이 아니면 null로 둬.\n\n"
        f"{truncated_text}"
    )


def _coerce_policy_summary(
    raw_summary: dict[str, object],
    insurer_candidates: tuple[str, ...],
) -> LlmPolicySummary:
    summary: LlmPolicySummary = {}

    for key in _SUMMARY_STRING_FIELDS:
        value = _coerce_non_empty_string(raw_summary.get(key))
        if value is None:
            continue
        if key == "보험사" and value not in insurer_candidates:
            continue
        summary[key] = value  # type: ignore[literal-required]

    coverage_period = _coerce_coverage_period(raw_summary.get("보험기간"))
    if coverage_period:
        summary["보험기간"] = coverage_period

    premium = _coerce_premium_summary(raw_summary.get("보험료"))
    if premium:
        summary["보험료"] = premium

    vehicle_info = _coerce_vehicle_info(raw_summary.get("차량정보"))
    if vehicle_info:
        summary["차량정보"] = vehicle_info

    return summary


def _coerce_coverage_period(value: object) -> CoveragePeriod | None:
    if not isinstance(value, dict):
        return None

    coverage_period: CoveragePeriod = {}
    start_date = _coerce_non_empty_string(value.get("시작일"))
    if start_date is not None:
        coverage_period["시작일"] = start_date

    end_date = _coerce_non_empty_string(value.get("종료일"))
    if end_date is not None:
        coverage_period["종료일"] = end_date

    return coverage_period or None


def _coerce_premium_summary(value: object) -> PremiumSummary | None:
    if not isinstance(value, dict):
        return None

    premium: PremiumSummary = {}
    amount = value.get("금액")
    if isinstance(amount, int):
        premium["금액"] = amount

    payment_cycle = _coerce_non_empty_string(value.get("납입주기"))
    if payment_cycle is not None:
        premium["납입주기"] = payment_cycle

    return premium or None


def _coerce_vehicle_info(value: object) -> VehicleInfo | None:
    if not isinstance(value, dict):
        return None

    vehicle_info: VehicleInfo = {}
    vehicle_name = _coerce_non_empty_string(value.get("차량명"))
    if vehicle_name is not None:
        vehicle_info["차량명"] = vehicle_name

    plate_number = _coerce_non_empty_string(value.get("차량번호"))
    if plate_number is not None:
        vehicle_info["차량번호"] = plate_number

    model_year = _coerce_non_empty_string(value.get("연식"))
    if model_year is not None:
        vehicle_info["연식"] = model_year

    return vehicle_info or None


def _coerce_non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    if normalized.lower() in {"null", "none", "n/a"} or normalized in {"없음", "미상"}:
        return None
    return normalized or None


# --------------------------------------------------------------------------
# Public orchestrator
# --------------------------------------------------------------------------

_LLM_FILLABLE_FIELDS = [
    "보험사",
    "상품명",
    "증권번호",
    "계약자",
    "피보험자",
    "보험기간",
    "만기일",
    "납입기간",
    "보험료",
    "차량정보",
]
_LLM_TRIGGER_FIELDS = [
    field for field in _LLM_FILLABLE_FIELDS if field not in {"보험사", "납입기간", "차량정보"}
]


def extract_policy_summary(
    text: str,
    llm_extractor: Callable[[str], LlmPolicySummary | None] | None = (
        extract_policy_summary_with_llm
    ),
) -> PolicySummary:
    summary = extract_local_policy_summary(text)
    masked_text = mask_demographic_identifiers(text)

    if llm_extractor and _needs_llm_fill(summary):
        _merge_missing_llm_fields(summary, llm_extractor(masked_text), text)

    classification = classify_policy(
        text=masked_text,
        product_name=summary.get("상품명"),
    )
    summary["보험분류"] = classification["보험분류"]
    summary["상품태그"] = classification["상품태그"]

    return summary


def _needs_llm_fill(summary: PolicySummary) -> bool:
    return any(field not in summary for field in _LLM_TRIGGER_FIELDS)


# Identity fields whose value must be traceable back to the source document.
# 보험기간/만기일/납입기간/보험료 are structured/derived (dates, amounts, periods)
# rather than free-text spans copied from the document, so they are excluded here.
_GROUNDED_LLM_FIELDS = {"보험사", "증권번호", "계약자", "피보험자", "상품명"}

# Generic industry suffixes of Korean insurer legal names, longest first. The
# catalog lists full legal names ("DB손해보험") while documents usually print
# only the brand ("DB" etc.), so insurer grounding checks the brand —
# the legal name minus one of these suffixes — instead of the full name.
_INSURER_NAME_SUFFIXES = (
    "화재해상보험",
    "해상화재보험",
    "손해보험",
    "생명보험",
    "화재보험",
    "해상보험",
    "화재",
    "생명",
    "보험",
)

_BRAND_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[가-힣]+")


def _insurer_grounded(candidate: str, text: str) -> bool:
    """True when the insurer's brand appears in the text (cite-or-refuse).

    The brand is the catalog legal name minus one generic industry suffix;
    every brand token of 2+ chars (alphanumeric or Hangul run) must appear in
    the whitespace-normalized text, in any position — documents may print the
    tokens apart ("NH", "농협금융지주"). Falls back to the full-name check when
    stripping leaves nothing usable.
    """
    brand = candidate
    for suffix in _INSURER_NAME_SUFFIXES:
        if brand.endswith(suffix) and len(brand) > len(suffix):
            brand = brand[: -len(suffix)]
            break

    tokens = [token for token in _BRAND_TOKEN_PATTERN.findall(brand) if len(token) >= 2]
    if not tokens:
        return wording_grounded(candidate, text)

    normalized_text = re.sub(r"\s", "", text).lower()
    return all(token.lower() in normalized_text for token in tokens)


def _merge_missing_llm_fields(
    summary: PolicySummary, llm_summary: LlmPolicySummary | None, text: str
) -> None:
    if not llm_summary:
        return

    for key in _LLM_FILLABLE_FIELDS:
        if key in summary or key not in llm_summary:
            continue

        value = llm_summary[key]  # type: ignore[literal-required]
        # Cite-or-refuse: an LLM-filled identity field must actually appear in the
        # source text. Without this check, a hallucinated value (e.g. an insurer
        # the enum permits but the document never names) would be surfaced as if
        # it were extracted from the policy itself. 보험사 is grounded on its
        # brand token (see _insurer_grounded) because documents print the brand,
        # not the catalog's full legal name.
        if key in _GROUNDED_LLM_FIELDS:
            if not isinstance(value, str):
                continue
            grounded = (
                _insurer_grounded(value, text) if key == "보험사" else wording_grounded(value, text)
            )
            if not grounded:
                continue

        # 차량정보 is a dict, not a plain string, so it can't share the
        # str-only grounding check above. Grounding target is the plate
        # (차량번호): if the LLM supplied one, it must appear in the source
        # text or the whole 차량정보 is dropped (cite-or-refuse). 차량명/연식
        # are lookup-style info (looked up from the plate, not copied verbatim
        # from the document), so a policy with no plate on file is accepted
        # as-is — there is nothing in the source text to ground them against.
        if key == "차량정보":
            if not isinstance(value, dict):
                continue
            plate_number = value.get("차량번호")
            if isinstance(plate_number, str) and not wording_grounded(plate_number, text):
                continue

        summary[key] = value  # type: ignore[literal-required]
