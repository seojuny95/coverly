"""Safety validators shared by generated consultation features."""

from collections.abc import Callable

_UNSUPPORTED_CONCLUSIONS = (
    "보험금이 지급",
    "보험금을 지급",
    "보상받을 수",
    "보상 받을 수",
    "면책이 없",
    "면책되지 않",
    "가입하면 됩니다",
    "반드시 가입",
    "공식 기준",
    "충분합니다",
    "부족합니다",
    "가족력이 있어",
    "부양가족이 있어",
    "자녀가 있어",
    "소득이 높",
    "소득이 낮",
)
_ADEQUACY_TERMS = (
    "충분",
    "부족",
    "적정",
    "권장",
    "추천",
    "최소",
    "필수",
    "무조건",
)
_NEUTRAL_ANALYSIS_TERMS = _ADEQUACY_TERMS + (
    "과다",
    "과소",
    "과도",
    "과한",
    "적절",
    "알맞",
    "높",
    "낮",
    "많아",
    "많은",
    "많습니다",
    "적어",
    "적은",
    "적습니다",
    "좋",
    "나쁘",
)
# Sales pushes that _DIRECT_ACTION_TERMS misses but are never acceptable — kept
# separate from adequacy words that grounded analysis may use in other contexts.
_SALES_PUSH_TERMS = (
    "반드시 가입",
    "꼭 가입",
    "가입하면 됩니다",
    "가입하는 것이 좋습니다",
    "추가 가입",
    "가입을 고려",
    "가입을 검토",
    "추가적인 보장",
    "필요한 보장",
)
_DIRECT_ACTION_TERMS = (
    "가입하세요",
    "가입해요",
    "가입해야",
    "해지하세요",
    "증액하세요",
    "감액하세요",
    "늘리세요",
    "줄이세요",
    "변경하세요",
)
_UNSUPPORTED_GUIDANCE_TERMS = _ADEQUACY_TERMS + (
    "늘리",
    "높이",
    "증액",
    "줄이",
    "낮추",
    "감액하",
    "가입하",
    "추가하",
    "해지하",
    "유지하",
    "바꾸",
    "변경하",
    "맞추",
    "확보하",
    "준비하",
    "좋습니다",
    "좋아요",
    "꼭 ",
)
_MONEY_UNITS = ("억원", "천만원", "백만원", "만원")
_PAYOUT_OR_OFFICIAL_CLAIMS = (
    "보험금이 지급",
    "보험금을 지급",
    "보상받을 수",
    "보상 받을 수",
    "보장받을 수",
    "보장 받을 수",
    "보장받는",
    "보장받고",
    "보장돼요",
    "지급됩니다",
    "지급돼요",
    "지원받을 수",
    "면책이 없",
    "면책되지 않",
    "공식 기준",
)
_OFFICIAL_CLAIMS = ("공식 기준",)
_PAYOUT_CLAIMS = tuple(term for term in _PAYOUT_OR_OFFICIAL_CLAIMS if term not in _OFFICIAL_CLAIMS)
_OFFICIAL_ADEQUACY_TERMS = ("충분", "부족", "적정", "권장", "추천")
_FABRICATED_PERSONAL_FACTS = (
    "가족력이 있어",
    "부양가족이 있어",
    "자녀가 있어",
    "소득이 높",
    "소득이 낮",
)
_UNSUPPORTED_PROMISES = (
    "안심하셔도",
    "확실히 갖추",
    "매우 강력",
    "추가로 고려",
    "어떤 상황에서도",
    "큰 도움이 될",
    "위험을 다양하게 분산",
)


def has_unsupported_conclusion(text: str) -> bool:
    compact = " ".join(text.split())
    return any(term in compact for term in _UNSUPPORTED_CONCLUSIONS)


def is_safe_confirmed_fact(text: str) -> bool:
    """Allow prose facts only when they avoid new numeric or claim conclusions."""

    cleaned = text.strip()
    return (
        bool(cleaned)
        and not any(character.isdigit() for character in cleaned)
        and not has_unsupported_conclusion(cleaned)
        and not any(term in cleaned for term in _ADEQUACY_TERMS)
        and not any(term in cleaned for term in _DIRECT_ACTION_TERMS)
    )


def is_safe_general_guidance(text: str) -> bool:
    """Allow non-numeric review guidance without adequacy claims or direct actions."""

    cleaned = text.strip()
    if not cleaned or has_unsupported_conclusion(cleaned):
        return False
    if any(character.isdigit() for character in cleaned):
        return False
    if any(unit in cleaned for unit in _MONEY_UNITS):
        return False
    return not any(term in cleaned for term in _UNSUPPORTED_GUIDANCE_TERMS)


def is_safe_analysis_text(text: str, *, allow_official_claims: bool = False) -> bool:
    """Allow grounded analysis while blocking unsafe claims and direct actions."""

    cleaned = text.strip()
    if not cleaned:
        return False
    compact = " ".join(cleaned.split())
    blocked_claims = _PAYOUT_CLAIMS if allow_official_claims else _PAYOUT_OR_OFFICIAL_CLAIMS
    if any(term in compact for term in blocked_claims):
        return False
    if any(term in compact for term in _UNSUPPORTED_PROMISES):
        return False
    if (
        allow_official_claims
        and "공식 기준" in compact
        and any(term in compact for term in _OFFICIAL_ADEQUACY_TERMS)
    ):
        return False
    if any(term in compact for term in _FABRICATED_PERSONAL_FACTS):
        return False
    if any(term in compact for term in _SALES_PUSH_TERMS):
        return False
    return not any(term in cleaned for term in _DIRECT_ACTION_TERMS)


def is_safe_neutral_analysis_text(text: str) -> bool:
    """Allow grounded analysis only when it avoids adequacy or value judgments."""

    cleaned = text.strip()
    return is_safe_analysis_text(cleaned) and not any(
        term in cleaned for term in _NEUTRAL_ANALYSIS_TERMS
    )


def filter_safe_unique_texts(
    items: list[str],
    *,
    is_safe: Callable[[str], bool],
) -> list[str]:
    accepted: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not is_safe(cleaned) or cleaned in accepted:
            continue
        accepted.append(cleaned)
    return accepted
