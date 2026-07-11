"""Extract a display-ready policy summary from parsed PDF text.

Combines three extraction layers into one flat module:
  1. Local (regex) extraction — fast, deterministic, works offline.
  2. LLM extraction — fills fields the regex layer could not find.
  3. Classification merge — attaches 보험분류/상품태그 via `classify_policy`.
"""

import json
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from openai.types.responses import EasyInputMessageParam, ResponseTextConfigParam

from app.services.classification import classify_policy
from app.services.grounding import wording_grounded
from app.services.types import CoveragePeriod, PolicyCoreSummary, PolicySummary, PremiumSummary
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
    r"계약자\s+([가-힣A-Za-z]+)\s+증권번호",
    rf"증권번호\s*{_POLICY_NUMBER_VALUE_PATTERN}\s*계약자\s*({_PERSON_NAME_VALUE_PATTERN})",
    rf"계약자\s*({_PERSON_NAME_VALUE_PATTERN})\s*\([^)]*\)\s*보험기간",
]
_INSURED_PERSON_EXTRACTION_PATTERNS = [
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


def _extract_insurer_name(text: str) -> str | None:
    return _extract_labeled_value(text, _INSURER_LABELS)


_PRODUCT_NAME_TRAILING_LABELS = _POLICY_NUMBER_LABELS + ["계약자", "보험기간"]


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
        _POLICY_NUMBER_LABELS + ["계약자", "보험기간"],
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
    resident-registration number, e.g. `가나(TESTBIRTH-D-1******)`. That value
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
    lines = _normalized_lines(text)
    for pattern in _POLICY_HOLDER_EXTRACTION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            candidate = _clean_value(match.group(1))
            if _valid_person_name(candidate):
                return candidate.split("(")[0].strip()

    for index, line in enumerate(lines):
        if line not in {"보험계약자", "계약자", "◆ 계약자"}:
            continue
        for offset in range(1, 3):
            next_index = index + offset
            if next_index >= len(lines):
                break
            candidate = _clean_value(lines[next_index])
            if _valid_person_name(candidate):
                return candidate.split("(")[0].strip()

    inline_value = _extract_between_markers(
        text,
        ["계약자"],
        ["보험기간", "증권번호", "피보험자", "계약사항", "만기보험금수익자"],
    )
    if inline_value:
        holder_match = re.match(rf"({_PERSON_NAME_VALUE_PATTERN})", inline_value)
        if holder_match and _valid_person_name(holder_match.group(1)):
            return holder_match.group(1)

    labeled_value = _extract_labeled_value(text, _POLICY_HOLDER_LABELS)
    if labeled_value and _valid_person_name(labeled_value):
        return labeled_value.split("(")[0].strip()

    return None


def _extract_insured_person(text: str) -> str | None:
    lines = _normalized_lines(text)
    for pattern in _INSURED_PERSON_EXTRACTION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            candidate = _clean_value(match.group(1))
            if _valid_person_name(candidate):
                return candidate.split("(")[0].strip()

    for index, line in enumerate(lines):
        if line not in {"기명피보험자", "피보험자성명", "(주)피보험자", "피보험자"}:
            continue
        for offset in range(1, 3):
            next_index = index + offset
            if next_index >= len(lines):
                break
            candidate = _clean_value(lines[next_index])
            if _valid_person_name(candidate):
                return candidate.split("(")[0].strip()

    inline_value = _extract_between_markers(
        text,
        _INSURED_PERSON_LABELS,
        ["판매플랜", "상해급수", "직업/직무", "운행차량", "보험기간", "가입담보", "증권번호"],
    )
    if inline_value:
        insured_match = re.match(rf"({_PERSON_NAME_VALUE_PATTERN})", inline_value)
        if insured_match and _valid_person_name(insured_match.group(1)):
            return insured_match.group(1)

    labeled_value = _extract_labeled_value(text, _INSURED_PERSON_LABELS)
    if labeled_value and _valid_person_name(labeled_value):
        return labeled_value.split("(")[0].strip()

    return None


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

    candidates = [re.search(pattern, text) for pattern in _PREMIUM_AMOUNT_PATTERNS]
    amount_match = next((match for match in candidates if match), None)
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
    for pattern in _PAYMENT_PERIOD_PATTERNS:
        match = re.search(pattern, text)
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

    for pattern in _PAYMENT_PERIOD_PATTERNS:
        match = re.search(pattern, contract_terms)
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

JsonObject = dict[str, Any]

_MAX_INPUT_CHARS = 30_000
_INSURER_CATALOG_PATH = Path(__file__).with_name("data") / "insurer_catalog.json"
_STRING_OR_NULL_SCHEMA: JsonObject = {"type": ["string", "null"]}
_INTEGER_OR_NULL_SCHEMA: JsonObject = {"type": ["integer", "null"]}
_SUMMARY_STRING_FIELDS = (
    "보험사",
    "상품명",
    "증권번호",
    "계약자",
    "피보험자",
    "만기일",
    "납입기간",
)
_SUMMARY_REQUIRED_FIELDS = [
    "보험사",
    "상품명",
    "증권번호",
    "계약자",
    "피보험자",
    "보험기간",
    "만기일",
    "납입기간",
    "보험료",
]
_SYSTEM_PROMPT = (
    "너는 한국 보험증권 PDF에서 표시용 핵심 필드만 추출한다. "
    "보험사는 보험계약을 인수하거나 증권을 발행한 보험회사명이다. "
    "상품명, 브랜드명, 플랜명, 부서명, 모집/품질보증 담당자명은 보험사가 아니다. "
    "보험사는 반드시 사용자가 제공한 후보 목록 중 하나만 선택한다. "
    "회사명이 그대로 적혀 있지 않으면 문서의 단서(로고 표기, 상품 브랜드, "
    "홈페이지 주소, 콜센터 안내 등)를 후보 목록과 연결해 판단하라. "
    "그래도 어느 후보인지 확인할 수 없으면 null로 둔다."
)


@lru_cache
def get_insurer_candidates() -> tuple[str, ...]:
    payload = json.loads(_INSURER_CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("insurer catalog must be a JSON list")

    candidates = tuple(value for value in payload if isinstance(value, str) and value.strip())
    if not candidates:
        raise ValueError("insurer catalog must contain at least one insurer")

    return candidates


@lru_cache
def _get_openai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def extract_policy_summary_with_llm(text: str) -> LlmPolicySummary | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None

    insurer_candidates = get_insurer_candidates()
    response_text = _request_summary_text(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        response_format=_build_response_format(insurer_candidates),
        messages=_build_messages(text, insurer_candidates),
    )
    if response_text is None:
        return None

    raw_summary = _parse_json_object(response_text)
    if raw_summary is None:
        return None

    return _coerce_policy_summary(raw_summary, insurer_candidates)


def _build_messages(text: str, insurer_candidates: tuple[str, ...]) -> list[EasyInputMessageParam]:
    insurer_list = "\n".join(f"- {insurer}" for insurer in insurer_candidates)
    truncated_text = text[:_MAX_INPUT_CHARS]

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "다음 텍스트에서 보험사, 상품명, 증권번호, 계약자, 피보험자, "
                "보험기간, 만기일, 납입기간, 보험료를 추출해.\n"
                "보험사 후보 목록:\n"
                f"{insurer_list}\n\n"
                "보험사에는 후보 목록에 없는 상품명이나 브랜드명을 넣지 마. "
                "후보 목록의 실제 보험회사와 명확히 연결되는 경우에만 후보명을 선택해.\n\n"
                f"{truncated_text}"
            ),
        },
    ]


def _build_response_format(insurer_candidates: tuple[str, ...]) -> JsonObject:
    return {
        "format": {
            "type": "json_schema",
            "name": "policy_summary_extraction",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "보험사": {
                        "type": ["string", "null"],
                        "enum": [*insurer_candidates, None],
                    },
                    "상품명": _STRING_OR_NULL_SCHEMA,
                    "증권번호": _STRING_OR_NULL_SCHEMA,
                    "계약자": _STRING_OR_NULL_SCHEMA,
                    "피보험자": _STRING_OR_NULL_SCHEMA,
                    "보험기간": _build_coverage_period_schema(),
                    "만기일": _STRING_OR_NULL_SCHEMA,
                    "납입기간": _STRING_OR_NULL_SCHEMA,
                    "보험료": _build_premium_schema(),
                },
                "required": _SUMMARY_REQUIRED_FIELDS,
            },
        }
    }


def _build_coverage_period_schema() -> JsonObject:
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "properties": {
            "시작일": _STRING_OR_NULL_SCHEMA,
            "종료일": _STRING_OR_NULL_SCHEMA,
        },
        "required": ["시작일", "종료일"],
    }


def _build_premium_schema() -> JsonObject:
    return {
        "type": ["object", "null"],
        "additionalProperties": False,
        "properties": {
            "금액": _INTEGER_OR_NULL_SCHEMA,
            "납입주기": _STRING_OR_NULL_SCHEMA,
        },
        "required": ["금액", "납입주기"],
    }


def _request_summary_text(
    *,
    api_key: str,
    model: str,
    response_format: JsonObject,
    messages: list[EasyInputMessageParam],
) -> str | None:
    client = _get_openai_client(api_key)

    try:
        response = client.responses.create(
            model=model,
            input=cast(Any, messages),
            text=cast(ResponseTextConfigParam, response_format),
            temperature=0,
        )
    except (APIConnectionError, APIStatusError, APITimeoutError):
        return None

    response_text = response.output_text
    if not isinstance(response_text, str):
        return None

    normalized = response_text.strip()
    return normalized or None


def _parse_json_object(value: str) -> JsonObject | None:
    try:
        parsed = json.loads(_strip_json_code_fence(value))
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def _strip_json_code_fence(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _coerce_policy_summary(
    raw_summary: JsonObject,
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


def _coerce_non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.strip()
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
]


def extract_policy_summary(
    text: str,
    llm_extractor: Callable[[str], LlmPolicySummary | None] | None = (
        extract_policy_summary_with_llm
    ),
) -> PolicySummary:
    summary = extract_local_policy_summary(text)

    if llm_extractor and _needs_llm_fill(summary):
        _merge_missing_llm_fields(summary, llm_extractor(text), text)

    classification = classify_policy(
        text=text,
        product_name=summary.get("상품명"),
    )
    summary["보험분류"] = classification["보험분류"]
    summary["상품태그"] = classification["상품태그"]

    return summary


def _needs_llm_fill(summary: PolicySummary) -> bool:
    return any(field not in summary for field in _LLM_FILLABLE_FIELDS)


# Identity fields whose value must be traceable back to the source document.
# 보험기간/만기일/납입기간/보험료 are structured/derived (dates, amounts, periods)
# rather than free-text spans copied from the document, so they are excluded here.
_GROUNDED_LLM_FIELDS = {"보험사", "증권번호", "계약자", "피보험자", "상품명"}

# Generic industry suffixes of Korean insurer legal names, longest first. The
# catalog lists full legal names ("DB손해보험") while documents usually print
# only the brand ("DB", "디비손보"), so insurer grounding checks the brand —
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

        summary[key] = value  # type: ignore[literal-required]
