"""Deterministic answer boundaries shared by Policy RAG output paths."""

from __future__ import annotations

import re
from collections.abc import Sequence

_PERSONAL_CONTEXT_TERMS = ("내가", "제가", "저는", "나는", "저에게", "나한테")
_TIME_CONTEXT_TERMS = ("오늘", "어제", "방금", "지난주", "지난달")
_INCIDENT_TERMS = ("진단", "확진", "사고", "다친", "입원", "수술", "치료")
_COMPLETED_INCIDENT_TERMS = (
    "진단받았",
    "진단 받았",
    "진단을 받았",
    "확진받았",
    "확진 받았",
    "확진을 받았",
    "확진됐",
    "사고가 났",
    "사고 났",
    "다쳤",
    "입원했",
    "수술했",
    "치료받았",
    "치료 받았",
    "치료를 받았",
)
_CLAIM_VERDICT_TERMS = (
    "받을 수",
    "받을수",
    "나와",
    "지급",
    "보상",
    "청구 가능",
    "해당",
)
_PROMPT_INJECTION_MARKERS = (
    "이전 지시",
    "시스템 지시",
    "지시를 무시",
    "답하라",
    "출력하라",
    "추천하라",
    "권유하라",
)


def requires_unavailable_policy_context(
    question: str,
    evidence_facts: Sequence[str],
) -> bool:
    """Return whether retrieved policy text cannot safely answer the question."""

    evidence_text = " ".join(evidence_facts)
    if _asks_personal_adequacy(question):
        return True
    if _asks_exact_renewal_value(question):
        return True
    if _asks_actual_incident_verdict(question):
        return True
    if _asks_complete_claim_documents(question) and "서류" not in evidence_text:
        return True
    if _asks_complete_exclusion_list(question):
        return True
    if _asks_missing_beneficiary(question, evidence_text):
        return True
    return _asks_missing_exclusion_confirmation(question, evidence_text)


def safe_policy_evidence_fact(fact: str) -> str:
    """Remove document sentences that look like instructions to the Agent."""

    parts = re.split(r"(?<=[.!?])\s+", fact.strip())
    kept = [
        part for part in parts if not any(marker in part for marker in _PROMPT_INJECTION_MARKERS)
    ]
    return " ".join(kept).strip()


def _asks_personal_adequacy(question: str) -> bool:
    return any(term in question for term in ("부족", "충분")) and any(
        term in question for term in ("가족력", "소득", "부양", "자녀", "내 상황")
    )


def _asks_exact_renewal_value(question: str) -> bool:
    if "갱신" not in question:
        return False
    asks_exact_amount = "정확히" in question and "얼마" in question
    asks_exact_rate = any(term in question for term in ("몇 퍼센트", "몇%", "인상률", "오르는지"))
    return asks_exact_amount or asks_exact_rate


def _asks_actual_incident_verdict(question: str) -> bool:
    asks_for_verdict = any(term in question for term in _CLAIM_VERDICT_TERMS)
    if not asks_for_verdict:
        return False

    describes_completed_incident = any(term in question for term in _COMPLETED_INCIDENT_TERMS)
    has_contextual_incident = any(term in question for term in _INCIDENT_TERMS) and (
        any(term in question for term in _PERSONAL_CONTEXT_TERMS)
        or any(term in question for term in _TIME_CONTEXT_TERMS)
    )
    return describes_completed_incident or has_contextual_incident


def _asks_complete_claim_documents(question: str) -> bool:
    return "서류" in question and any(
        term in question for term in ("정확히", "전부", "모두", "빠짐없이")
    )


def _asks_complete_exclusion_list(question: str) -> bool:
    asks_exclusions = any(term in question for term in ("제외", "면책", "보상하지"))
    asks_complete_list = any(term in question for term in ("모든", "전부", "전체", "빠짐없이"))
    return asks_exclusions and asks_complete_list


def _asks_missing_beneficiary(question: str, evidence_text: str) -> bool:
    if any(term in question for term in ("확인되는 것만", "확인된 것만")):
        return False
    if not any(term in question for term in ("수익자", "누가 받", "누구에게 지급")):
        return False
    return "수익자" not in evidence_text


def _asks_missing_exclusion_confirmation(question: str, evidence_text: str) -> bool:
    if not any(term in question for term in ("제외", "면책", "보상하지")):
        return False
    return not any(term in evidence_text for term in ("제외", "면책", "보상하지"))
