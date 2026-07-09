import re

from app.services.policy_summary_types import CoveragePeriod, PolicySummary, PremiumSummary

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
_HYUNDAI_POLICY_NUMBER_VALUE_PATTERN = r"\b([A-Z]\d{4}[A-Z0-9*\-]{6,})\b"
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
    _HYUNDAI_POLICY_NUMBER_VALUE_PATTERN,
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
_PREMIUM_AMOUNT_PATTERNS = [
    r"납입보험료\s*[:：]?\s*([\d,]+)원",
    r"1회 보험료\s*([\d,\s]+)원",
    r"납입한 보험료\s*(?:\(총보험료\)\s*)?([\d,]+)원",
    r"보험료\s*([\d,]+)원",
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

    maturity_date = _extract_maturity_date(text, coverage_period)
    if maturity_date:
        summary["만기일"] = maturity_date

    premium = _extract_premium(text)
    if premium:
        summary["보험료"] = premium

    payment_period = _extract_payment_period(text)
    if payment_period:
        summary["납입기간"] = payment_period

    _apply_hyundai_auto_layout_overrides(text, summary)
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


def _extract_product_name(text: str) -> str | None:
    explicit_name = _extract_labeled_value(text, _PRODUCT_NAME_LABELS)
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
    if inline_name:
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
        if inline_match:
            return _clean_value(inline_match.group(0))

    for index, line in enumerate(lines):
        if "증권번호" not in line and "계약번호" not in line:
            continue
        for offset in range(1, 5):
            next_index = index + offset
            if next_index >= len(lines):
                break
            candidate_match = policy_number_pattern.search(lines[next_index])
            if candidate_match:
                return _clean_value(candidate_match.group(0))

    return _extract_labeled_value(text, _POLICY_NUMBER_LABELS)


def _extract_policy_holder(text: str) -> str | None:
    lines = _normalized_lines(text)
    for pattern in _POLICY_HOLDER_EXTRACTION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return _clean_value(match.group(1))

    for index, line in enumerate(lines):
        if line not in {"보험계약자", "계약자", "◆ 계약자"}:
            continue
        for offset in range(1, 3):
            next_index = index + offset
            if next_index >= len(lines):
                break
            candidate = _clean_value(lines[next_index])
            if re.fullmatch(_PERSON_NAME_WITH_OPTIONAL_PAREN_PATTERN, candidate):
                return candidate.split("(")[0].strip()

    inline_value = _extract_between_markers(
        text,
        ["계약자"],
        ["보험기간", "증권번호", "피보험자", "계약사항", "만기보험금수익자"],
    )
    if inline_value:
        holder_match = re.match(rf"({_PERSON_NAME_VALUE_PATTERN})", inline_value)
        if holder_match:
            return holder_match.group(1)

    return _extract_labeled_value(text, _POLICY_HOLDER_LABELS)


def _extract_insured_person(text: str) -> str | None:
    lines = _normalized_lines(text)
    for pattern in _INSURED_PERSON_EXTRACTION_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return _clean_value(match.group(1))

    for index, line in enumerate(lines):
        if line not in {"기명피보험자", "피보험자성명", "(주)피보험자", "피보험자"}:
            continue
        for offset in range(1, 3):
            next_index = index + offset
            if next_index >= len(lines):
                break
            candidate = _clean_value(lines[next_index])
            if re.fullmatch(_PERSON_NAME_WITH_OPTIONAL_PAREN_PATTERN, candidate):
                return candidate.split("(")[0].strip()

    inline_value = _extract_between_markers(
        text,
        _INSURED_PERSON_LABELS,
        ["판매플랜", "상해급수", "직업/직무", "운행차량", "보험기간", "가입담보", "증권번호"],
    )
    if inline_value:
        insured_match = re.match(rf"({_PERSON_NAME_VALUE_PATTERN})", inline_value)
        if insured_match:
            return insured_match.group(1)

    return _extract_labeled_value(text, _INSURED_PERSON_LABELS)


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


def _extract_maturity_date(
    text: str,
    coverage_period: CoveragePeriod | None,
) -> str | None:
    del text

    if coverage_period and coverage_period.get("종료일"):
        return coverage_period["종료일"]
    return None


def _apply_hyundai_auto_layout_overrides(text: str, summary: PolicySummary) -> None:
    lines = _normalized_lines(text)
    try:
        holder_header_index = lines.index("보험계약자 보험계약자주소")
        insured_header_index = lines.index("기명피보험자 피보험자주소")
    except ValueError:
        return

    table_value_lines = lines[holder_header_index + 3 : insured_header_index + 8]
    if len(table_value_lines) < 6:
        return

    if summary.get("증권번호") in {None, "발행일"}:
        policy_number_match = re.search(
            _HYUNDAI_POLICY_NUMBER_VALUE_PATTERN,
            " ".join(table_value_lines),
        )
        if policy_number_match:
            summary["증권번호"] = policy_number_match.group(1)

    holder_match = re.match(rf"({_PERSON_NAME_VALUE_PATTERN})\(", table_value_lines[2])
    if holder_match:
        summary["계약자"] = holder_match.group(1)

    insured_match = re.match(rf"({_PERSON_NAME_VALUE_PATTERN})\(", table_value_lines[4])
    if insured_match:
        summary["피보험자"] = insured_match.group(1)

    if "보험기간" not in summary:
        period_match = re.search(
            r"(20\d{2}-\d{2}-\d{2})\s*~\s*(20\d{2}-\d{2}-\d{2})",
            " ".join(table_value_lines),
        )
        if period_match:
            summary["보험기간"] = {
                "시작일": period_match.group(1),
                "종료일": period_match.group(2),
            }

    if summary.get("상품명") in _GENERIC_PRODUCT_NAMES | {None} and len(table_value_lines) >= 6:
        product_name = _clean_value(table_value_lines[5])
        if product_name and product_name not in {"관계자", "차량사항"}:
            summary["상품명"] = product_name
