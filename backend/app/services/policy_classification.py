from typing import TypedDict


class PolicyClassification(TypedDict):
    보험분류: str
    상품태그: list[str]


# Consumer-facing buckets are based on KNIA product guide groupings.
# Sources checked 2026-07-09:
# - KNIA FAQ product buckets:
#   https://consumer.knia.or.kr/consumer/center/faq.do
#   (자동차 / 상해·질병·실손 / 저축·연금 / 배상·화재·기타)
# - KNIA long-term product guide:
#   https://consumer.knia.or.kr/consumer/insurance-guide/0201.do
#   (화재보험 / 종합보험 / 상해‧질병보험 / 간병보험 / 비용보험 / 실손의료보험)
# - Insurance Business Act Article 2 and 4:
#   https://www.law.go.kr/lsLinkProc.do?efYd=20140410&joNo=000200&lnkJoNo=undefined&lsClsCd=L&lsId=prec20140410&lsNm=%EB%B3%B4%ED%97%98%EC%97%85%EB%B2%95&mode=11
#   https://www.law.go.kr/lsLawLinkInfo.do?chrClsCd=010202&lsJoLnkSeq=1000734825
# Project-specific adaptation:
# We keep a dedicated 생명·연금 bucket because life-product naming (종신/정기/연금)
# is explicit in market practice even though KNIA's consumer buckets focus on
# non-life products.
CLASSIFICATION_AUTO = "자동차"
CLASSIFICATION_HEALTH = "상해·질병·실손"
CLASSIFICATION_LIFE = "생명·연금"
CLASSIFICATION_OTHER = "배상·화재·기타"
CLASSIFICATION_UNKNOWN = "미분류"

TAG_ORDER = [
    "자동차",
    "실손",
    "암",
    "상해",
    "질병",
    "간병",
    "운전자",
    "화재",
    "배상책임",
    "종신",
    "정기",
    "연금",
    "어린이",
]

_AUTO_PRODUCT_TERMS = [
    "자동차보험",
    "개인용자동차보험",
    "하이카",
    "hicar",
]
_AUTO_COVERAGE_TERMS = [
    "대인배상",
    "대물배상",
    "자기차량손해",
    "무보험차상해",
    "자기신체사고",
    "자동차상해",
]

_INDEMNITY_TERMS = [
    "실손의료보험",
    "실손의료비",
    "실비보험",
    "급여",
    "비급여",
    "자기부담금",
]

_DRIVER_PRODUCT_TERMS = ["운전자보험", "운전자"]
_DRIVER_COVERAGE_TERMS = [
    "벌금",
    "변호사선임비용",
    "교통사고처리지원금",
]

_FIRE_PRODUCT_TERMS = [
    "화재보험",
    "주택화재",
]
_FIRE_COVERAGE_TERMS = [
    "화재손해",
    "화재배상책임",
]
_FIRE_TERMS = [
    "화재보험",
    "화재손해",
    "주택화재",
    "화재배상책임",
]
_LIABILITY_TERMS = [
    "배상책임",
    "임차자배상책임",
]

_LIFE_TERMS = {
    "종신": ["종신보험", "종신"],
    "정기": ["정기보험", "정기"],
    "연금": ["연금보험", "연금"],
}

_HEALTH_PRODUCT_TAG_TERMS = {
    "암": ["암보험", "암진단비"],
    "상해": ["상해보험", "상해", "후유장해"],
    "질병": ["건강보험", "질병", "뇌혈관질환", "허혈성심질환", "질병입원일당"],
    "간병": ["간병보험", "치매", "장기요양", "간병자금"],
    "어린이": ["어린이보험", "자녀"],
}


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def _count_matches(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term in text)


def _add_tag(tags: list[str], tag: str) -> None:
    if tag not in tags:
        tags.append(tag)


def classify_policy(
    text: str,
    product_name: str | None = None,
    insurer_name: str | None = None,
) -> PolicyClassification:
    del insurer_name

    normalized_text = "".join(text.split()).lower()
    normalized_product_name = (product_name or "").replace(" ", "").lower()
    search_space = f"{normalized_product_name}\n{normalized_text}".strip()
    tags: list[str] = []

    auto_strength = _count_matches(
        search_space,
        [term.lower() for term in _AUTO_PRODUCT_TERMS],
    )
    auto_strength += _count_matches(
        normalized_text,
        [term.lower() for term in _AUTO_COVERAGE_TERMS],
    )

    driver_product_hits = _count_matches(
        normalized_product_name, [term.lower() for term in _DRIVER_PRODUCT_TERMS]
    )
    driver_strength = driver_product_hits * 2
    driver_strength += _count_matches(
        normalized_text,
        [term.lower() for term in _DRIVER_COVERAGE_TERMS],
    )

    indemnity_strength = _count_matches(
        normalized_text,
        [term.lower() for term in _INDEMNITY_TERMS],
    )
    if normalized_product_name and _contains_any(
        normalized_product_name, [term.lower() for term in _INDEMNITY_TERMS]
    ):
        indemnity_strength += 2

    fire_product_hits = _count_matches(
        normalized_product_name, [term.lower() for term in _FIRE_PRODUCT_TERMS]
    )
    fire_strength = fire_product_hits * 2
    fire_strength += _count_matches(
        normalized_text,
        [term.lower() for term in _FIRE_COVERAGE_TERMS],
    )
    liability_strength = _count_matches(
        normalized_text, [term.lower() for term in _LIABILITY_TERMS]
    )

    life_tags_found: list[str] = []
    for tag, terms in _LIFE_TERMS.items():
        if _contains_any(normalized_product_name, [term.lower() for term in terms]):
            life_tags_found.append(tag)

    health_tags_found: list[str] = []
    for tag, terms in _HEALTH_PRODUCT_TAG_TERMS.items():
        if _contains_any(search_space, [term.lower() for term in terms]):
            health_tags_found.append(tag)

    if driver_strength >= 2:
        _add_tag(tags, "운전자")
        return {
            "보험분류": CLASSIFICATION_OTHER,
            "상품태그": tags,
        }

    if auto_strength >= 3:
        _add_tag(tags, "자동차")
        return {
            "보험분류": CLASSIFICATION_AUTO,
            "상품태그": tags,
        }

    if life_tags_found:
        for tag in TAG_ORDER:
            if tag in life_tags_found:
                _add_tag(tags, tag)
        return {
            "보험분류": CLASSIFICATION_LIFE,
            "상품태그": tags,
        }

    if indemnity_strength >= 2:
        _add_tag(tags, "실손")
        return {
            "보험분류": CLASSIFICATION_HEALTH,
            "상품태그": tags,
        }

    if fire_product_hits >= 1 or (fire_strength + liability_strength) >= 2:
        _add_tag(tags, "화재")
        if liability_strength >= 1:
            _add_tag(tags, "배상책임")
        return {
            "보험분류": CLASSIFICATION_OTHER,
            "상품태그": tags,
        }

    if liability_strength >= 2:
        _add_tag(tags, "배상책임")
        return {
            "보험분류": CLASSIFICATION_OTHER,
            "상품태그": tags,
        }

    if health_tags_found:
        for tag in TAG_ORDER:
            if tag in health_tags_found:
                _add_tag(tags, tag)
        return {
            "보험분류": CLASSIFICATION_HEALTH,
            "상품태그": tags,
        }

    return {
        "보험분류": CLASSIFICATION_UNKNOWN,
        "상품태그": tags,
    }
