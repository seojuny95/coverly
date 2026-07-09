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
# - Insurance Supervision Regulation Enforcement Rules attached table 14:
#   https://law.go.kr/flDownload.do?bylClsCd=200201&flNm=%5B%EB%B3%84%ED%91%9C+14%5D+%ED%91%9C%EC%A4%80%EC%82%AC%EC%97%85%EB%B0%A9%EB%B2%95%EC%84%9C%28%EC%A0%9C5-13%EC%A1%B0%EA%B4%80%EB%A0%A8%29&flSeq=157366267
_POLICY_DOCUMENT_TERMS = [
    "보험증권",
    "보험가입증서",
    "증권번호",
    "계약자",
    "피보험자",
    "보험기간",
    "보험료",
    "보험금액",
]

_MIN_POLICY_SIGNAL_SCORE = 4


def classify_policy_document(text: str) -> PolicyDocumentSignal:
    normalized = "".join(text.split())
    matched_terms = [term for term in _POLICY_DOCUMENT_TERMS if term in normalized]
    return PolicyDocumentSignal(
        is_likely_policy=len(matched_terms) >= _MIN_POLICY_SIGNAL_SCORE,
        score=len(matched_terms),
        matched_terms=matched_terms,
    )
