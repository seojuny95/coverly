"""Situation-based descriptions of what each coverage category prepares for.

Framed by the real-life situation the coverage addresses — NOT by adequacy —
so the copy passes is_safe_confirmed_fact (no digits, adequacy terms, money
units, or action verbs). This is what turns "가입 사실 확인" into a reason.
"""

from app.services.coverage_knowledge import taxonomy as coverage_taxonomy

_PURPOSES: dict[str, str] = {
    coverage_taxonomy.CANCER: "암을 진단받은 초기에 목돈이 드는 상황에 대응하는 성격이에요.",
    coverage_taxonomy.CEREBRO: ("뇌혈관 질환을 진단받았을 때의 목돈 부담에 대응하는 성격이에요."),
    coverage_taxonomy.HEART: "심장 질환을 진단받았을 때의 목돈 부담에 대응하는 성격이에요.",
    coverage_taxonomy.INJURY_DISABILITY: (
        "사고로 장해가 남아 소득이 줄어드는 상황에 대응하는 성격이에요."
    ),
    coverage_taxonomy.DISEASE_DISABILITY: (
        "질병으로 장해가 남아 소득이 줄어드는 상황에 대응하는 성격이에요."
    ),
    coverage_taxonomy.HOSPITAL: "입원해 있는 동안 병원비와 생활비 부담을 메우는 성격이에요.",
    coverage_taxonomy.SURGERY: "수술을 받을 때 드는 비용 부담을 덜어 주는 성격이에요.",
    coverage_taxonomy.DEATH: (
        "가장의 부재로 남은 가족의 생계가 흔들리는 상황에 대응하는 성격이에요."
    ),
    coverage_taxonomy.INDEMNITY: (
        "실제 지출한 치료비를 돌려받아 병원비 부담을 덜어 주는 성격이에요."
    ),
    coverage_taxonomy.CARE: "혼자 일상생활이 어려워 간병이 필요한 상황에 대응하는 성격이에요.",
}


def coverage_purpose(category: str) -> str | None:
    """Return the situation this category prepares for, or None if unknown."""

    return _PURPOSES.get(category)
