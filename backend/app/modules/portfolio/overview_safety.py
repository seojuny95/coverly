"""Deterministic safety checks for generated portfolio overview copy."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_NUMBER_PATTERN = re.compile(r"\d")
_KOREAN_AMOUNT_PATTERN = re.compile(r"[영일이삼사오육칠팔구십백천만억]+(?:원|만원|억원)")
_PROHIBITED_PATTERNS = (
    re.compile(r"(?:가입|해지|유지).{0,8}(?:해야|하세요|권해|권장|추천|필요)"),
    re.compile(r"(?:증액|감액|늘려야|줄여야)"),
    re.compile(
        r"(?:충분|부족|적정|과도|완벽|든든)"
        r"(?:하게|히)?.{0,4}(?:해요|돼요|합니다|하다고|해보여요|준비됐어요)"
    ),
    re.compile(r"보험금.{0,12}(?:받을 수|지급돼|나와|나옵니다)"),
    re.compile(r"(?:혜택|손해를 봐|큰일)"),
)


@dataclass(frozen=True)
class OverviewCopySegment:
    slot_id: str
    text: str
    limitation: str | None = None


def overview_copy_is_safe(
    *,
    title: str,
    title_slot_id: str,
    paragraphs: Sequence[OverviewCopySegment],
    terms_by_slot: Mapping[str, frozenset[str]],
) -> bool:
    """Reject unsupported judgments and facts assigned to another slot."""

    if not _text_is_safe(title):
        return False
    if _mentions_terms_from_another_slot(title, title_slot_id, terms_by_slot):
        return False

    for paragraph in paragraphs:
        if not _text_is_safe(paragraph.text):
            return False
        if _mentions_terms_from_another_slot(
            paragraph.text,
            paragraph.slot_id,
            terms_by_slot,
        ):
            return False
        if paragraph.limitation is not None:
            if not _text_is_safe(paragraph.limitation):
                return False
            if paragraph.slot_id.startswith("unconfirmed:") and not _is_clear_limitation(
                paragraph.limitation
            ):
                return False
    return True


def _text_is_safe(text: str) -> bool:
    if _NUMBER_PATTERN.search(text) or _KOREAN_AMOUNT_PATTERN.search(text):
        return False
    return not any(pattern.search(text) for pattern in _PROHIBITED_PATTERNS)


def _mentions_terms_from_another_slot(
    text: str,
    slot_id: str,
    terms_by_slot: Mapping[str, frozenset[str]],
) -> bool:
    normalized_text = _normalize(text)
    allowed_terms = terms_by_slot.get(slot_id, frozenset())
    for other_slot_id, terms in terms_by_slot.items():
        if other_slot_id == slot_id:
            continue
        for term in terms - allowed_terms:
            if term in normalized_text:
                return True
    return False


def _is_clear_limitation(text: str) -> bool:
    normalized = _normalize(text)
    return all(term in normalized for term in ("현재자료", "미가입", "단정"))


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()
