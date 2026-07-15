import os
from collections.abc import Callable

import pytest

# Unit tests must remain deterministic even when a developer has DATABASE_URL configured.
os.environ["REFERENCE_DATA_DATABASE_ENABLED"] = "false"


_REFERENCE_DATA_ROWS: dict[str, object] = {
    "insurer_catalog": [
        "AXA손해보험",
        "DB손해보험",
        "메리츠화재",
        "KDB생명",
        "한화손해보험",
        "교보생명",
        "삼성화재",
        "흥국생명",
        "흥국화재",
        "현대해상화재보험",
        "KB손해보험",
        "미래에셋생명",
        "더케이손해보험",
        "롯데손해보험",
        "캐롯손해보험",
        "메트라이프생명",
        "하나손해보험",
        "MG손해보험",
        "예별손해보험",
        "NH농협생명",
        "NH농협손해보험",
        "AIA생명",
        "ABL생명",
    ],
    "claim_channels": {
        "보험사": [
            {
                "보험사": "삼성화재",
                "고객센터": "1588-5114",
                "홈페이지": "https://www.samsungfire.com",
                "청구링크": "https://www.samsungfire.com",
                "앱": "삼성화재",
                "비고": "홈페이지 > 보험금청구",
                "source": "https://www.samsungfire.com",
            },
            {
                "보험사": "현대해상",
                "고객센터": "1588-5656",
                "홈페이지": "https://www.hi.co.kr",
                "청구링크": "https://www.hi.co.kr",
                "앱": "현대해상 모바일 앱",
                "source": "https://www.hi.co.kr",
            },
            {
                "보험사": "DB손해보험",
                "고객센터": "1588-0100",
                "홈페이지": "https://www.idbins.com",
                "청구링크": "https://www.idbins.com",
                "앱": "DB손해보험",
                "source": "https://m.directdb.co.kr/comm/spt/serviceGuideView.do",
            },
            {
                "보험사": "메리츠화재",
                "고객센터": "1566-7711",
                "홈페이지": "https://www.meritzfire.com",
                "청구링크": "https://www.meritzfire.com",
                "source": "https://www.meritzfire.com",
            },
            {
                "보험사": "흥국화재",
                "고객센터": "1688-1688",
                "홈페이지": "https://www.heungkukfire.co.kr",
                "청구링크": "https://www.heungkukfire.co.kr/FRW/compensation/carCompInfo.do",
                "source": "https://www.heungkukfire.co.kr",
            },
        ],
        "실손": {
            "이름": "실손24",
            "설명": "실손보험금 청구 공식 서비스",
            "콜센터": "1811-3000",
            "채널": [
                {"이름": "실손24 홈페이지", "링크": "https://www.silson24.or.kr"},
            ],
        },
    },
    "disclosure_links": {
        "association_links": [
            {
                "kind": "life",
                "name": "생명보험협회 공시실",
                "url": "https://www.klia.or.kr/",
                "description": "생명보험 상품공시와 약관 확인 경로",
            },
            {
                "kind": "non_life",
                "name": "손해보험협회 소비자포털 공시정보",
                "url": "https://consumer.knia.or.kr/disclosure.do",
                "description": "손해보험 상품공시와 약관 확인 경로",
            },
            {
                "kind": "integrated",
                "name": "보험다모아",
                "url": "https://e-insmarket.or.kr/",
                "description": "보험상품 비교공시 경로",
            },
        ],
    },
    "essential_coverage_guides": {
        "sources": [
            {
                "id": "kca_funeral_cost_2004",
                "label": "한국소비자원 · 평균 장례비용 조사",
                "url": "https://www.kca.go.kr/home/sub.do?menukey=4002&mode=view&no=1000396173&page=148",
                "published_at": "2004-09-22",
                "reliability": "official",
                "caveat": "장례비용은 시기, 지역, 장례 방식에 따라 달라질 수 있어요.",
            },
            {
                "id": "bizwatch_cancer_diagnosis_2024_07",
                "label": "비즈워치 · 암 진단비 평균 범위",
                "url": "https://news.bizwatch.co.kr/article/finance/2024/07/05/0038",
                "published_at": "2024-07-06",
                "reliability": "private_guidance",
                "caveat": "암 진단비 금액은 소득, 가족 부양, 보험료 부담에 따라 달라질 수 있어요.",
            },
            {
                "id": "banksalad_three_diagnosis_2026",
                "label": "뱅크샐러드 · 3대 진단비 구성 예시",
                "url": "https://www.banksalad.com/articles/%EB%B3%B4%ED%97%98-%EC%A2%85%ED%95%A9%EB%B3%B4%ED%97%98-%EC%A7%88%EB%B3%B4%ED%97%98",
                "published_at": "2026-07-01",
                "reliability": "private_guidance",
                "caveat": "구성 예시는 상품과 개인 상황에 따라 달라질 수 있어요.",
            },
            {
                "id": "silson24_official",
                "label": "실손24 · 서비스 안내",
                "url": "https://www.silson24.or.kr",
                "published_at": "2025-01-01",
                "reliability": "official",
                "caveat": (
                    "실손 청구 가능 범위는 의료기관과 보험회사 시스템에 따라 달라질 수 있어요."
                ),
            },
        ],
        "items": [
            {
                "kind": "death",
                "reference_min_amount": 10_000_000,
                "reference_max_amount": 20_000_000,
                "basis": "장례비와 초기 정리 비용을 먼저 보는 점검용 범위",
                "source_ids": ["kca_funeral_cost_2004"],
            },
            {
                "kind": "cancer",
                "reference_min_amount": 30_000_000,
                "reference_max_amount": 50_000_000,
                "basis": "암 진단비는 치료 중 쉬는 기간의 생활비 성격까지 고려하는 기본 범위",
                "source_ids": [
                    "bizwatch_cancer_diagnosis_2024_07",
                    "banksalad_three_diagnosis_2026",
                ],
            },
            {
                "kind": "cerebrovascular",
                "reference_min_amount": 10_000_000,
                "reference_max_amount": 20_000_000,
                "basis": "뇌혈관질환 진단비는 재활, 간병, 후유장해 가능성을 고려하는 기본 범위",
                "source_ids": ["banksalad_three_diagnosis_2026"],
            },
            {
                "kind": "ischemic_heart",
                "reference_min_amount": 10_000_000,
                "reference_max_amount": 20_000_000,
                "basis": (
                    "심장질환 진단비는 시술, 수술, 입원으로 생길 수 있는 "
                    "소득 공백을 고려하는 기본 범위"
                ),
                "source_ids": ["banksalad_three_diagnosis_2026"],
            },
            {
                "kind": "medical_indemnity",
                "reference_min_amount": None,
                "reference_max_amount": None,
                "basis": ("실손의료보험은 금액보다 가입 여부, 세대, 자기부담금, 중복 여부를 확인"),
                "source_ids": ["silson24_official"],
            },
        ],
    },
    "death_benefit_guides": {
        "sources": [
            {
                "id": "mk_death_income_multiple_2020",
                "label": "매일경제 · 가장의 적정 사망보험금은 연소득 3~5배",
                "url": "https://www.mk.co.kr/news/economy/9495174",
                "published_at": "2020-08-28",
                "reliability": "private_guidance",
                "caveat": (
                    "민간 재무설계 관점의 일반 가이드이며 개인별 적정 보험금의 공식 기준은 아니다."
                ),
            },
            {
                "id": "mk_death_income_debt_2019",
                "label": "매일경제 · 종신보험 보장금 수준, 연봉 3배+대출금 적당",
                "url": "https://www.mk.co.kr/news/economy/8884760",
                "published_at": "2019-07-05",
                "reliability": "private_guidance",
                "caveat": (
                    "민간 재무설계 관점의 일반 가이드이며 "
                    "부채와 가족 상황을 함께 보라는 참고 자료다."
                ),
            },
        ],
        "guides": [
            {
                "has_dependent_family": False,
                "has_minor_children": False,
                "has_major_debt": False,
                "situation": "부양가족이나 큰 부채가 없는 경우",
                "amount_label": "0원~5천만 원",
                "min_amount": 0,
                "max_amount": 50_000_000,
                "reason": (
                    "사망보험금은 남은 가족의 생활비 공백을 메우는 목적이 크기 때문에, "
                    "부양가족이나 큰 부채가 없다면 큰 금액의 필요성은 낮아요. "
                    "장례비, 정리비, 부모 지원 정도만 고려하면 돼요."
                ),
                "source_ids": [
                    "mk_death_income_multiple_2020",
                    "mk_death_income_debt_2019",
                ],
            },
            {
                "has_dependent_family": True,
                "has_minor_children": False,
                "has_major_debt": False,
                "situation": "배우자나 가족이 내 소득에 일부 의존하는 경우",
                "amount_label": "5천만~1.5억 원",
                "min_amount": 50_000_000,
                "max_amount": 150_000_000,
                "reason": (
                    "갑작스러운 소득 공백이 생길 수 있으므로 일정 기간의 생활비가 필요해요. "
                    "다만 미성년 자녀나 큰 부채가 없다면 장기간의 고액 보장보다는 "
                    "1년 안팎의 생활비 수준이 현실적이에요."
                ),
                "source_ids": [
                    "mk_death_income_multiple_2020",
                    "mk_death_income_debt_2019",
                ],
            },
            {
                "has_dependent_family": False,
                "has_minor_children": True,
                "has_major_debt": False,
                "situation": "자녀 양육비와 교육비가 남아 있는 경우",
                "amount_label": "1억~2억 원",
                "min_amount": 100_000_000,
                "max_amount": 200_000_000,
                "reason": (
                    "미성년 자녀가 있으면 양육비와 교육비가 계속 발생해요. "
                    "다만 다른 소득원이 있거나 부채가 크지 않다면, "
                    "기본 생활비와 교육비 일부를 보완하는 수준으로 볼 수 있어요."
                ),
                "source_ids": [
                    "mk_death_income_multiple_2020",
                    "mk_death_income_debt_2019",
                ],
            },
            {
                "has_dependent_family": True,
                "has_minor_children": True,
                "has_major_debt": False,
                "situation": "가족 생활비와 자녀 양육비를 함께 책임지는 경우",
                "amount_label": "2억~3억 원",
                "min_amount": 200_000_000,
                "max_amount": 300_000_000,
                "reason": (
                    "가족이 내 소득에 의존하고 미성년 자녀도 있다면 "
                    "생활비, 양육비, 교육비 공백이 함께 생겨요. "
                    "국내 재무설계 기준에서 자주 언급되는 연소득 3~5배 또는 "
                    "생활비 3년치 기준을 적용하면 2억~3억 원이 현실적인 기본 범위예요."
                ),
                "source_ids": [
                    "mk_death_income_multiple_2020",
                    "mk_death_income_debt_2019",
                ],
            },
            {
                "has_dependent_family": False,
                "has_minor_children": False,
                "has_major_debt": True,
                "situation": "주담대·전세대출 등 갚아야 할 큰 부채가 있는 경우",
                "amount_label": "5천만~1.5억 원 + 부채 고려",
                "min_amount": 50_000_000,
                "max_amount": 150_000_000,
                "reason": (
                    "부양가족이 없더라도 대출이 남아 있다면 "
                    "가족이나 상속인이 정리해야 할 부담이 생길 수 있어요. "
                    "기본 정리비용에 부채 일부 또는 전액을 추가로 고려하는 게 좋아요."
                ),
                "source_ids": [
                    "mk_death_income_multiple_2020",
                    "mk_death_income_debt_2019",
                ],
            },
            {
                "has_dependent_family": True,
                "has_minor_children": False,
                "has_major_debt": True,
                "situation": "가족 생활비와 대출 부담이 함께 남는 경우",
                "amount_label": "1.5억~3억 원",
                "min_amount": 150_000_000,
                "max_amount": 300_000_000,
                "reason": (
                    "내 소득이 사라지면 가족의 생활비와 대출 상환 부담이 동시에 남아요. "
                    "그래서 단순 생활비보다 더 높은 보장이 필요할 수 있고, "
                    "대출 규모에 따라 3억 원 안팎까지 검토할 수 있어요."
                ),
                "source_ids": [
                    "mk_death_income_multiple_2020",
                    "mk_death_income_debt_2019",
                ],
            },
            {
                "has_dependent_family": False,
                "has_minor_children": True,
                "has_major_debt": True,
                "situation": "자녀 양육비와 대출 부담이 함께 남는 경우",
                "amount_label": "2억~4억 원",
                "min_amount": 200_000_000,
                "max_amount": 400_000_000,
                "reason": (
                    "자녀가 있으면 양육비·교육비가 계속 들고, "
                    "여기에 주담대나 전세대출까지 있으면 남은 가족의 부담이 커져요. "
                    "생활비 3년치에 부채를 더하는 방식으로 보면 2억 원 이상이 필요할 수 있어요."
                ),
                "source_ids": [
                    "mk_death_income_multiple_2020",
                    "mk_death_income_debt_2019",
                ],
            },
            {
                "has_dependent_family": True,
                "has_minor_children": True,
                "has_major_debt": True,
                "situation": "가족 생활비, 자녀 양육비, 대출 부담을 모두 책임지는 경우",
                "amount_label": "3억~5억 원",
                "min_amount": 300_000_000,
                "max_amount": 500_000_000,
                "reason": (
                    "가장의 소득 공백, 자녀 양육비·교육비, 대출 상환 부담이 모두 남는 상황이에요. "
                    "이 경우 사망보험금은 단순 장례비가 아니라 가족이 몇 년간 생활을 유지하고 "
                    "부채를 정리할 수 있는 금액이어야 하므로 3억~5억 원 수준을 검토할 수 있어요."
                ),
                "source_ids": [
                    "mk_death_income_multiple_2020",
                    "mk_death_income_debt_2019",
                ],
            },
        ],
    },
}


def _cache_clear(target: Callable[..., object]) -> None:
    cache_clear = getattr(target, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()


@pytest.fixture(autouse=True)
def database_reference_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide deterministic Supabase-owned reference rows to unit tests."""

    from app.modules.coverage import disclosure_links
    from app.modules.policy.summary import catalog
    from app.modules.portfolio import death_benefit_guides, essential_guides
    from app.modules.qa import claim_channels
    from app.modules.reference_data import loader as reference_data

    _cache_clear(reference_data._database_reference_data)
    _cache_clear(disclosure_links._directory)
    _cache_clear(claim_channels._directory)
    _cache_clear(catalog.get_insurer_candidates)
    _cache_clear(catalog.get_insurer_aliases)
    _cache_clear(catalog.get_insurer_contact_evidence)
    _cache_clear(death_benefit_guides._guide_rows)
    _cache_clear(essential_guides.essential_coverage_guides)

    monkeypatch.setattr(reference_data, "_database_reference_data", lambda: _REFERENCE_DATA_ROWS)
