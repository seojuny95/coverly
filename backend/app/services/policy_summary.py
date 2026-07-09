import re
from typing import TypedDict

from app.services.policy_classification import classify_policy


class CoveragePeriod(TypedDict, total=False):
    시작일: str
    종료일: str


class PremiumSummary(TypedDict, total=False):
    금액: int
    납입주기: str


class PolicySummary(TypedDict, total=False):
    보험사: str
    상품명: str
    증권번호: str
    계약자: str
    피보험자: str
    보험기간: CoveragePeriod
    만기일: str
    납입기간: str
    보험료: PremiumSummary
    보험분류: str
    상품태그: list[str]


_FIELD_LABELS: dict[str, list[str]] = {
    "보험사": ["보험사", "회사명", "발행회사"],
    "상품명": ["상품명", "상품명칭", "플랜명", "보험종목"],
    "증권번호": ["증권번호", "보험증권번호", "계약번호"],
    "계약자": ["보험계약자", "계약자"],
    "피보험자": ["기명피보험자", "피보험자성명", "(주)피보험자", "피보험자"],
}

_ALL_LABELS = [
    *{label for labels in _FIELD_LABELS.values() for label in labels},
    "보험기간",
    "보험료",
]
_ALL_LABEL_PATTERN = "|".join(re.escape(label) for label in _ALL_LABELS)
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

            match = re.match(rf"^{re.escape(label)}\s*[:：]?\s*(.+)$", line)
            if match:
                candidate = _clean_value(match.group(1))
                if candidate:
                    return candidate
    return None


def _extract_insurer_name(text: str) -> str | None:
    known_insurer_patterns = [
        ("NH농협손해보험", ["NH농협손해보험", "www.nhfire.co.kr", "NH가성비굿플러스"]),
        ("흥국화재", ["흥국화재해상보험주식회사", "흥국화재", "www.heungkukfire.co.kr"]),
        ("현대해상화재보험", ["Hyundai Marine & Fire Insurance", "Hicar", "하이카서비스"]),
        ("DB손해보험", ["www.idbins.com", "프로미라이프", "참좋은운전자상해보험"]),
    ]
    for insurer_name, patterns in known_insurer_patterns:
        if any(pattern in text for pattern in patterns):
            return insurer_name
    return _extract_labeled_value(text, _FIELD_LABELS["보험사"])


def _extract_product_name(text: str) -> str | None:
    explicit_name = _extract_labeled_value(text, _FIELD_LABELS["상품명"])
    if explicit_name:
        return explicit_name

    product_patterns = [
        r"보험종목\s*(무배당.+?)\s*증권번호",
        r"보험증권(?:\[보험가입증서\])?\s*(무배당.+?)(?:\n|\[모바일약관\]|계약자)",
    ]
    for pattern in product_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            candidate = _clean_value(match.group(1))
            if candidate and candidate not in {"보험", "보험증권"}:
                return candidate

    inline_name = _extract_between_markers(
        text,
        _FIELD_LABELS["상품명"],
        _FIELD_LABELS["증권번호"] + ["계약자", "보험기간"],
    )
    if inline_name:
        return inline_name

    lines = _normalized_lines(text)
    for line in lines:
        candidate = _clean_value(line)
        if candidate.startswith("(무)") or candidate.startswith("무배당 "):
            return candidate
    for index, line in enumerate(lines):
        if line in {"보험증권", "보 험 증 권"} and index + 1 < len(lines):
            candidate = _clean_value(lines[index + 1])
            if candidate.startswith("무배당"):
                return candidate
    return None


def _extract_policy_number(text: str) -> str | None:
    lines = _normalized_lines(text)
    policy_number_pattern = re.compile(r"[A-Z0-9*][A-Z0-9*\-]{5,}")

    patterns = [
        r"계약번호\s*[:：]?\s*([A-Z0-9*][A-Z0-9*\-]{5,})",
        r"증권번호\s*[:：]?\s*([A-Z0-9*][A-Z0-9*\-]{5,})",
        r"계약자\s+[가-힣A-Za-z]+\s+증권번호\s+([A-Z0-9*][A-Z0-9*\-]{5,})",
        r"\b([A-Z]\d{4}[A-Z0-9*\-]{6,})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_value(match.group(1))

    inline_value = _extract_between_markers(
        text,
        _FIELD_LABELS["증권번호"],
        _FIELD_LABELS["계약자"] + _FIELD_LABELS["피보험자"] + ["보험기간", "보험료"],
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

    return _extract_labeled_value(text, _FIELD_LABELS["증권번호"])


def _extract_policy_holder(text: str) -> str | None:
    lines = _normalized_lines(text)
    patterns = [
        r"계약자\s+([가-힣A-Za-z]+)\s+증권번호",
        r"증권번호\s*[A-Z0-9*][A-Z0-9*\-]{5,}\s*계약자\s*([가-힣A-Za-z]{2,})",
        r"계약자\s*([가-힣A-Za-z]{2,})\s*\([^)]*\)\s*보험기간",
    ]
    for pattern in patterns:
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
            if re.fullmatch(r"[가-힣A-Za-z]+(?:\([^)]+\))?", candidate):
                return candidate.split("(")[0].strip()

    inline_value = _extract_between_markers(
        text,
        ["계약자"],
        ["보험기간", "증권번호", "피보험자", "계약사항", "만기보험금수익자"],
    )
    if inline_value:
        holder_match = re.match(r"([가-힣A-Za-z]{2,})", inline_value)
        if holder_match:
            return holder_match.group(1)

    return _extract_labeled_value(text, _FIELD_LABELS["계약자"])


def _extract_insured_person(text: str) -> str | None:
    lines = _normalized_lines(text)
    patterns = [
        r"피보험자\s+([가-힣A-Za-z]+)\s+주민등록번호",
        r"피보험자\s*([가-힣A-Za-z]{2,})\s*\(",
    ]
    for pattern in patterns:
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
            if re.fullmatch(r"[가-힣A-Za-z]+(?:\([^)]+\))?", candidate):
                return candidate.split("(")[0].strip()

    inline_value = _extract_between_markers(
        text,
        _FIELD_LABELS["피보험자"],
        [
            "판매플랜",
            "상해급수",
            "직업/직무",
            "운행차량",
            "보험기간",
            "가입담보",
            "증권번호",
        ],
    )
    if inline_value:
        insured_match = re.match(r"([가-힣A-Za-z]{2,})", inline_value)
        if insured_match:
            return insured_match.group(1)

    return _extract_labeled_value(text, _FIELD_LABELS["피보험자"])


def _normalize_date(value: str) -> str | None:
    match = re.search(r"(20\d{2})[.\-/년 ]\s*(\d{1,2})[.\-/월 ]\s*(\d{1,2})", value)
    if not match:
        return None

    year, month, day = match.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _extract_period(text: str) -> CoveragePeriod | None:
    lines = _normalized_lines(text)
    collapsed = " ".join(lines)
    date_pattern = r"(?:20\d{2})[.\-/년 ]\s*\d{1,2}[.\-/월 ]\s*\d{1,2}(?:일)?"

    match = re.search(
        r"(20\d{2})년(\d{2})월(\d{2})일\s*부터\s*(20\d{2})년(\d{2})월(\d{2})일",
        collapsed,
    )
    if match:
        return {
            "시작일": f"{match.group(1)}-{match.group(2)}-{match.group(3)}",
            "종료일": f"{match.group(4)}-{match.group(5)}-{match.group(6)}",
        }

    match = re.search(
        r"보험기간\s*[:：]?\s*(20\d{2})(\d{2})(\d{2})~(20\d{2})(\d{2})(\d{2})",
        collapsed,
    )
    if match:
        return {
            "시작일": f"{match.group(1)}-{match.group(2)}-{match.group(3)}",
            "종료일": f"{match.group(4)}-{match.group(5)}-{match.group(6)}",
        }

    match = re.search(
        rf"보험기간\s*[:：]?\s*({date_pattern})\s*(?:~|-|부터)\s*({date_pattern})",
        collapsed,
    )
    if not match:
        inline_value = _extract_between_markers(
            collapsed,
            ["보험기간"],
            _SECTION_BOUNDARIES,
        )
        if inline_value:
            match = re.search(rf"({date_pattern})\s*(?:~|-|부터)\s*({date_pattern})", inline_value)
    if not match:
        return None

    start_date = _normalize_date(match.group(1))
    end_date = _normalize_date(match.group(2))
    if not start_date or not end_date:
        return None
    return {"시작일": start_date, "종료일": end_date}


def _extract_premium(text: str) -> PremiumSummary | None:
    match = re.search(r"([\d,]+)원\s*(월납|연납|일시납)", text)
    if match:
        return {
            "금액": int(match.group(1).replace(",", "")),
            "납입주기": match.group(2),
        }

    candidates = [
        re.search(r"납입보험료\s*[:：]?\s*([\d,]+)원", text),
        re.search(r"1회 보험료\s*([\d,\s]+)원", text),
        re.search(r"납입한 보험료\s*(?:\(총보험료\)\s*)?([\d,]+)원", text),
        re.search(r"보험료\s*([\d,]+)원", text),
    ]
    amount_match = next((match for match in candidates if match), None)
    if not amount_match:
        raw_value = _extract_labeled_value(text, ["보험료", "월보험료", "납입보험료"])
        if not raw_value:
            return None
        amount_match = re.search(r"(\d[\d,]*)\s*원", raw_value)
        if not amount_match:
            return None
        raw_cycle_source = raw_value
    else:
        raw_cycle_source = text[max(0, amount_match.start() - 16) : amount_match.end() + 32]

    cycle = ""
    if "일시납" in raw_cycle_source:
        cycle = "일시납"
    elif "연납" in raw_cycle_source or "연 " in raw_cycle_source:
        cycle = "연납"
    elif "월납" in raw_cycle_source or "월 " in raw_cycle_source:
        cycle = "월납"
    elif contract_terms := _extract_between_markers(
        text,
        ["계약사항"],
        ["만기보험금수익자", "가입정보", "보험료"],
    ):
        if "일시납" in contract_terms:
            cycle = "일시납"
        elif "연납" in contract_terms:
            cycle = "연납"
        elif "월납" in contract_terms:
            cycle = "월납"

    premium: PremiumSummary = {
        "금액": int(re.sub(r"\s+", "", amount_match.group(1)).replace(",", ""))
    }
    if cycle:
        premium["납입주기"] = cycle
    return premium


def _extract_payment_period(text: str) -> str | None:
    patterns = [
        r"\b(\d+년납)\b",
        r"\b(전기납)\b",
        r"\b(일시납)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    collapsed = " ".join(_normalized_lines(text))
    contract_terms = _extract_between_markers(
        collapsed,
        ["계약사항"],
        ["만기보험금수익자", "가입정보", "보험료", "담보정보"],
    )
    if contract_terms:
        for pattern in patterns:
            match = re.search(pattern, contract_terms)
            if match:
                return match.group(1)

    return None


def _extract_maturity_date(
    text: str,
    coverage_period: CoveragePeriod | None,
) -> str | None:
    if coverage_period and coverage_period.get("종료일"):
        return coverage_period["종료일"]

    if re.search(r"\b종신\b", text):
        return None

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
            r"\b([A-Z]\d{4}[A-Z0-9*\-]{6,})\b",
            " ".join(table_value_lines),
        )
        if policy_number_match:
            summary["증권번호"] = policy_number_match.group(1)

    holder_match = re.match(r"([가-힣A-Za-z]+)\(", table_value_lines[2])
    if holder_match:
        summary["계약자"] = holder_match.group(1)

    insured_match = re.match(r"([가-힣A-Za-z]+)\(", table_value_lines[4])
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

    if summary.get("상품명") in {None, "보험", "보험증권"}:
        for line in table_value_lines:
            if line.startswith("Hicar "):
                summary["상품명"] = line
                break


def extract_policy_summary(text: str) -> PolicySummary:
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

    classification = classify_policy(
        text=text,
        product_name=summary.get("상품명"),
        insurer_name=summary.get("보험사"),
    )
    summary["보험분류"] = classification["보험분류"]
    summary["상품태그"] = classification["상품태그"]

    return summary
