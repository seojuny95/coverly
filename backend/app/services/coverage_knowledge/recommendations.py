"""Age-band coverage recommendation heuristics for portfolio review.

This module is intentionally deterministic and framed as a private guide.
It is used to compare uploaded policies against a simple age-band checklist,
not to recommend a purchase or declare adequacy.
"""

from dataclasses import dataclass

from app.services.coverage_knowledge import taxonomy
from app.services.coverage_knowledge.purpose import coverage_purpose


@dataclass(frozen=True)
class AgeBandRecommendation:
    age_band_label: str
    title: str
    core_categories: tuple[str, ...]
    optional_categories: tuple[str, ...] = ()
    summary: str = ""


_BANKSALAD_REFERENCE_URL = (
    "https://www.banksalad.com/articles/"
    "%EB%B3%B4%ED%97%98-%EB%B3%B4%ED%97%98%EB%A6%AC%EB%AA%A8%EB%8D%B8%EB%A7%81-"
    "%EB%B3%B4%ED%97%98%EB%A3%8C"
)


def recommendation_for_age(age: int | None) -> AgeBandRecommendation | None:
    if age is None:
        return None
    if age < 40:
        return AgeBandRecommendation(
            age_band_label="20~30대",
            title="실손 + 3대 진단비를 먼저 보는 구간이에요",
            core_categories=(
                taxonomy.INDEMNITY,
                taxonomy.CANCER,
                taxonomy.CEREBRO,
                taxonomy.HEART,
            ),
            summary=(
                "민간 가이드에서는 아직 보험이 많지 않은 시기에는 실손과 "
                "암·뇌혈관·심장 진단비를 기본 축으로 먼저 보도록 설명해요."
            ),
        )
    if age < 60:
        return AgeBandRecommendation(
            age_band_label="40~50대",
            title="실손 + 3대 진단비에 수술비까지 같이 보는 구간이에요",
            core_categories=(
                taxonomy.INDEMNITY,
                taxonomy.CANCER,
                taxonomy.CEREBRO,
                taxonomy.HEART,
                taxonomy.SURGERY,
            ),
            summary=(
                "민간 가이드에서는 실손과 3대 진단비에 더해 수술비를 함께 점검하는 "
                "구간으로 설명해요."
            ),
        )
    return AgeBandRecommendation(
        age_band_label="60대 이상",
        title="실손 + 3대 진단비를 우선 보고 간병은 여유가 되면 함께 봐요",
        core_categories=(
            taxonomy.INDEMNITY,
            taxonomy.CANCER,
            taxonomy.CEREBRO,
            taxonomy.HEART,
        ),
        optional_categories=(taxonomy.CARE,),
        summary=(
            "민간 가이드에서는 실손과 3대 진단비를 먼저 보고, 간병은 납입 여력에 따라 "
            "추가로 점검할 수 있는 항목으로 설명해요."
        ),
    )


def recommendation_source() -> dict[str, str]:
    return {
        "label": "뱅크샐러드 · 연령별 필수 보험 가이드",
        "url": _BANKSALAD_REFERENCE_URL,
        "published_at": "2025-01-01",
        "reliability": "private_guidance",
        "caveat": "민간 가이드예요. 가입 권유나 개인별 충분·부족 판정 기준은 아니에요.",
    }


def recommendation_reason(category: str) -> str:
    purpose = coverage_purpose(category)
    if purpose:
        return purpose
    return "이 연령대에서 자주 같이 점검하는 기본 보장 묶음에 들어가요."
