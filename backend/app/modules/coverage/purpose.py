"""Situation-based descriptions of what each coverage category prepares for.

Framed by the real-life situation the coverage addresses — NOT by adequacy —
so the copy passes is_safe_confirmed_fact (no digits, adequacy terms, money
units, or action verbs). This is what turns "가입 사실 확인" into a reason.
"""

from app.modules.coverage import taxonomy as coverage_taxonomy

_PURPOSES: dict[str, str] = {
    coverage_taxonomy.CANCER: (
        "암 진단 초기에 필요한 치료 준비금과 생활비 공백을 살펴볼 때 기준이 돼요."
    ),
    coverage_taxonomy.CEREBRO: (
        "뇌혈관 질환 진단 후 치료와 회복 기간에 필요한 목돈을 점검할 때 중요해요."
    ),
    coverage_taxonomy.HEART: "심장 질환 진단 후 치료비와 회복 기간의 지출 부담을 볼 때 참고돼요.",
    coverage_taxonomy.INJURY_DISABILITY: (
        "사고 후 장해가 남아 소득이 줄거나 돌봄 비용이 생길 때를 살펴보는 항목이에요."
    ),
    coverage_taxonomy.DISEASE_DISABILITY: (
        "질병 후 장해로 일상생활이나 소득 흐름이 달라질 때 필요한 보장을 점검하게 해줘요."
    ),
    coverage_taxonomy.HOSPITAL: "입원 기간의 병원비와 생활비 부담을 함께 살펴보는 항목이에요.",
    coverage_taxonomy.SURGERY: "수술 시 발생하는 비용 부담을 점검하는 항목이에요.",
    coverage_taxonomy.DEATH: (
        "남은 가족의 생활비와 고정 지출을 이어갈 수 있는지 볼 때 핵심이 되는 항목이에요."
    ),
    coverage_taxonomy.INDEMNITY: (
        "실제 치료비 부담을 약관상 조건, 한도, 자기부담금과 함께 확인해야 하는 보장이에요."
    ),
    coverage_taxonomy.CARE: "혼자 일상생활이 어려워 간병비가 생길 때 부담을 점검하는 항목이에요.",
}


def coverage_purpose(category: str) -> str | None:
    """Return the situation this category prepares for, or None if unknown."""

    return _PURPOSES.get(category)
