import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDocumentSignal:
    is_likely_policy: bool
    score: int
    matched_terms: list[str]


# Gate terms are based on official policy/certificate fields, not a coverage taxonomy.
# Sources checked 2026-07-09:
# - Commercial Act Article 666:
#   https://www.law.go.kr/lsLawLinkInfo.do?chrClsCd=010202&lsJoLnkSeq=900420141
# - Commercial Act Article 728:
#   https://www.law.go.kr/LSW//lsLawLinkInfo.do?chrClsCd=010202&lsJoLnkSeq=900420244
# - Insurance Supervision Regulation Enforcement Rules attached table 14:
#   https://www.law.go.kr/admRulBylInfoPLinkR.do?admRulNm=%EB%B3%B4%ED%97%98%EC%97%85%EA%B0%90%EB%8F%85%EC%97%85%EB%AC%B4%EC%8B%9C%ED%96%89%EC%84%B8%EC%B9%99&bylBrNo=00&bylCls=BE&bylNo=0014
_POSITIVE_TERM_WEIGHTS: dict[str, int] = {
    "보험증권": 4,
    "보험가입증서": 4,
    "증권번호": 3,
    "계약번호": 3,
    "보험종목": 2,
    "계약자": 2,
    "피보험자": 2,
    "피보험자성명": 2,
    "기명피보험자": 2,
    "보험기간": 2,
    "보험계약일": 2,
    "계약만기일": 2,
    "보험료": 2,
    "1회보험료": 2,
    "납입보험료": 2,
    "납입한보험료": 2,
    "보장내용": 2,
    "보험금액": 2,
    "보험수익자": 1,
}

_NEGATIVE_TERM_WEIGHTS: dict[str, int] = {
    "개인정보처리방침": 5,
    "회의록": 4,
    "의사록": 4,
    "상품설명서": 3,
    "상품요약서": 3,
    "청약서": 2,
    "청약철회": 2,
    "안내문": 1,
    "참석자": 1,
    "안건": 1,
}

_DATE_PATTERN = r"(20\d{2})[.\-/년 ]\s*\d{1,2}[.\-/월 ]\s*\d{1,2}(?:일)?"
_POLICY_NUMBER_PATTERN = r"[A-Z0-9*][A-Z0-9*\-]{5,}"
_AMOUNT_PATTERN = r"\d[\d,\s]*원"

_STRUCTURAL_PATTERNS: list[tuple[str, int, str]] = [
    (
        "증권번호값",
        3,
        rf"(?:증권번호|계약번호)\s*[:：]?\s*{_POLICY_NUMBER_PATTERN}",
    ),
    (
        "보험기간값",
        3,
        rf"보험기간\s*[:：]?\s*{_DATE_PATTERN}\s*(?:~|-|부터)\s*{_DATE_PATTERN}",
    ),
    (
        "보험료값",
        2,
        rf"(?:보험료|1회\s*보험료|납입보험료|납입한\s*보험료)\s*[:：]?"
        rf"[\(\)\[\]\/0-9,\s가-힣A-Za-z-]*{_AMOUNT_PATTERN}",
    ),
    (
        "계약자값",
        2,
        r"(?:^|[\s:：])(보험계약자|계약자)\s*[:：]?\s*[가-힣A-Za-z]{2,}",
    ),
    (
        "피보험자값",
        2,
        r"(?:피보험자성명|기명피보험자|피보험자)\s*[:：]?\s*[가-힣A-Za-z]{2,}",
    ),
]

_REQUIRED_CORE_MATCHES = {"보험증권", "보험가입증서", "증권번호", "계약번호", "증권번호값"}
_MIN_POLICY_SIGNAL_SCORE = 8
_MIN_STRUCTURAL_MATCHES = 2


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def classify_policy_document(text: str) -> PolicyDocumentSignal:
    normalized = "".join(text.split())

    positive_matches = [term for term in _POSITIVE_TERM_WEIGHTS if term in normalized]
    positive_score = sum(_POSITIVE_TERM_WEIGHTS[term] for term in positive_matches)

    structural_matches = [
        label for label, _weight, pattern in _STRUCTURAL_PATTERNS if re.search(pattern, text)
    ]
    structural_score = sum(
        weight for label, weight, _pattern in _STRUCTURAL_PATTERNS if label in structural_matches
    )

    negative_matches = [term for term in _NEGATIVE_TERM_WEIGHTS if term in normalized]
    negative_score = sum(_NEGATIVE_TERM_WEIGHTS[term] for term in negative_matches)

    score = positive_score + structural_score - negative_score
    matched_terms = _unique(positive_matches + structural_matches)

    has_core_identifier = any(match in matched_terms for match in _REQUIRED_CORE_MATCHES)
    is_likely_policy = (
        score >= _MIN_POLICY_SIGNAL_SCORE
        and len(structural_matches) >= _MIN_STRUCTURAL_MATCHES
        and has_core_identifier
    )

    return PolicyDocumentSignal(
        is_likely_policy=is_likely_policy,
        score=score,
        matched_terms=matched_terms if is_likely_policy else matched_terms,
    )
